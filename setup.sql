-- Create table to track sync status
CREATE TABLE IF NOT EXISTS sync_status (
    table_name VARCHAR(255) PRIMARY KEY,
    last_sync_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on last_sync_time for better performance
CREATE INDEX IF NOT EXISTS idx_sync_status_last_sync_time 
ON sync_status(last_sync_time);
