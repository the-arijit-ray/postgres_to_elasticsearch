import os
import time
import yaml
import logging
from dotenv import load_dotenv
from sync_manager import PostgresElasticsearchSync

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from config.yaml and .env files"""
    # Load environment variables
    load_dotenv()
    
    # Load sync configuration
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    return config['sync_config']

def get_database_configs():
    """Get database configurations from environment variables"""
    pg_config = {
        'host': os.getenv('PG_HOST'),
        'port': int(os.getenv('PG_PORT', 5432)),
        'database': os.getenv('PG_DATABASE'),
        'user': os.getenv('PG_USER'),
        'password': os.getenv('PG_PASSWORD')
    }
    
    es_config = {
        'host': os.getenv('ES_HOST'),
        'port': int(os.getenv('ES_PORT', 9200)),
        'user': os.getenv('ES_USER'),
        'password': os.getenv('ES_PASSWORD'),
        'use_ssl': os.getenv('ES_USE_SSL', 'false').lower() == 'true'
    }
    
    return pg_config, es_config

def main():
    try:
        # Load configurations
        sync_config = load_config()
        pg_config, es_config = get_database_configs()
        
        # Validate configurations
        if not sync_config['tables']:
            logger.error("No tables configured for syncing")
            return
        
        logger.info("Starting PostgreSQL to Elasticsearch sync process")
        
        while True:
            try:
                with PostgresElasticsearchSync(pg_config, es_config, sync_config) as syncer:
                    for table_config in sync_config['tables']:
                        logger.info(f"Syncing table: {table_config['name']}")
                        syncer.sync_table(table_config)
                
                # Wait for next sync interval
                time.sleep(sync_config['sync_interval'])
                
            except Exception as e:
                logger.error(f"Error during sync process: {str(e)}")
                # Wait before retrying
                time.sleep(5)
                
    except KeyboardInterrupt:
        logger.info("Sync process stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")

if __name__ == "__main__":
    main()
