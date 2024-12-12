import os
import time
import logging
from datetime import datetime
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from tenacity import retry, stop_after_attempt, wait_exponential
from ratelimit import limits, sleep_and_retry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PostgresElasticsearchSync:
    def __init__(self, pg_config, es_config, sync_config):
        self.pg_config = pg_config
        self.es_config = es_config
        self.sync_config = sync_config
        self.pool = None
        self.es_client = None
        self.setup_connections()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def setup_connections(self):
        """Initialize connection pool and Elasticsearch client with retry logic"""
        try:
            # Create connection pool
            self.pool = SimpleConnectionPool(
                1, self.sync_config.get('pool_size', 5),
                host=self.pg_config['host'],
                port=self.pg_config['port'],
                dbname=self.pg_config['database'],
                user=self.pg_config['user'],
                password=self.pg_config['password']
            )
            
            es_hosts = [
                {
                    'host': self.es_config['host'],
                    'port': self.es_config['port'],
                    'scheme': 'https' if self.es_config['use_ssl'] else 'http'
                }
            ]
            
            self.es_client = Elasticsearch(
                es_hosts,
                basic_auth=(self.es_config['user'], self.es_config['password'])
            )
            
            logger.info("Successfully connected to PostgreSQL and Elasticsearch")
        except Exception as e:
            logger.error(f"Error connecting to databases: {str(e)}")
            raise

    def get_table_schema(self, table_name):
        """Fetch the current schema of a PostgreSQL table"""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                return {row[0]: row[1] for row in cursor.fetchall()}
        finally:
            self.pool.putconn(conn)

    def calculate_batch_size(self, table_name, timestamp_column):
        """Dynamically calculate batch size based on remaining records"""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Get total remaining records
                cursor.execute(f"""
                    SELECT COUNT(*)
                    FROM {table_name}
                    WHERE {timestamp_column} > (
                        SELECT COALESCE(
                            (SELECT last_sync_time 
                             FROM sync_status 
                             WHERE table_name = %s),
                            '1970-01-01'::timestamp
                        )
                    )
                """, (table_name,))
                remaining_records = cursor.fetchone()[0]

                # Calculate optimal batch size
                min_size = self.sync_config.get('min_batch_size', 100)
                max_size = self.sync_config.get('max_batch_size', 5000)
                
                if remaining_records <= min_size:
                    return min_size
                elif remaining_records <= max_size:
                    return remaining_records
                else:
                    # Use a logarithmic scale for larger datasets
                    import math
                    batch_size = min(
                        max_size,
                        int(min_size * math.log10(remaining_records))
                    )
                    return batch_size
        finally:
            self.pool.putconn(conn)

    @sleep_and_retry
    @limits(calls=1000, period=60)  # Rate limit: 1000 records per minute
    def sync_batch(self, actions):
        """Rate-limited bulk sync to Elasticsearch"""
        return bulk(
            self.es_client,
            actions,
            raise_on_error=False,
            raise_on_exception=False
        )

    def create_es_mapping(self, table_name, schema):
        """Create or update Elasticsearch mapping based on PostgreSQL schema"""
        pg_to_es_type = {
            'integer': 'integer',
            'bigint': 'long',
            'smallint': 'short',
            'decimal': 'double',
            'numeric': 'double',
            'real': 'float',
            'double precision': 'double',
            'character varying': 'keyword',
            'text': 'text',
            'boolean': 'boolean',
            'timestamp without time zone': 'date',
            'timestamp with time zone': 'date',
            'date': 'date',
            'jsonb': 'object',
            'json': 'object',
        }

        properties = {}
        for column, data_type in schema.items():
            es_type = pg_to_es_type.get(data_type.lower(), 'keyword')
            properties[column] = {'type': es_type}
            
            # Add keyword subfield for text fields for better sorting and aggregations
            if es_type == 'text':
                properties[column]['fields'] = {
                    'keyword': {'type': 'keyword', 'ignore_above': 256}
                }

        return {'properties': properties}

    def sync_table(self, table_config):
        """Sync a single table from PostgreSQL to Elasticsearch using server-side cursors"""
        table_name = table_config['name']
        index_name = table_config['index_name']
        timestamp_column = table_config['timestamp_column']
        
        try:
            # Get and update schema
            schema = self.get_table_schema(table_name)
            mapping = self.create_es_mapping(table_name, schema)
            
            if not self.es_client.indices.exists(index=index_name):
                self.es_client.indices.create(index=index_name, mappings=mapping)
            else:
                self.es_client.indices.put_mapping(index=index_name, body=mapping)

            # Calculate optimal batch size
            batch_size = self.calculate_batch_size(table_name, timestamp_column)
            logger.info(f"Using batch size of {batch_size} for table {table_name}")

            conn = self.pool.getconn()
            try:
                # Use server-side cursor for efficient memory usage
                with conn.cursor(
                    name='table_sync_cursor',
                    cursor_factory=RealDictCursor
                ) as cursor:
                    cursor.itersize = batch_size
                    cursor.execute(f"""
                        SELECT *
                        FROM {table_name}
                        WHERE {timestamp_column} > (
                            SELECT COALESCE(
                                (SELECT last_sync_time 
                                 FROM sync_status 
                                 WHERE table_name = %s),
                                '1970-01-01'::timestamp
                            )
                        )
                        ORDER BY {timestamp_column}
                    """, (table_name,))

                    while True:
                        rows = cursor.fetchmany(batch_size)
                        if not rows:
                            break

                        actions = [
                            {
                                '_index': index_name,
                                '_id': str(row[table_config['primary_key']]),
                                '_source': dict(row)
                            }
                            for row in rows
                        ]

                        success, failed = self.sync_batch(actions)
                        
                        logger.info(f"Synced {success} documents for table {table_name}")
                        if failed:
                            logger.error(f"Failed to sync {len(failed)} documents")

                        # Update sync status
                        with conn.cursor() as status_cursor:
                            status_cursor.execute("""
                                INSERT INTO sync_status (table_name, last_sync_time)
                                VALUES (%s, %s)
                                ON CONFLICT (table_name) 
                                DO UPDATE SET last_sync_time = EXCLUDED.last_sync_time
                            """, (table_name, datetime.now()))
                            conn.commit()

            finally:
                self.pool.putconn(conn)

        except Exception as e:
            logger.error(f"Error syncing table {table_name}: {str(e)}")
            raise

    def close_connections(self):
        """Close all database connections"""
        if self.pool:
            self.pool.closeall()
        if self.es_client:
            self.es_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connections()
