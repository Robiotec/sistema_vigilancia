-- Add server_ip and server_port fields to rboxes table
ALTER TABLE rboxes
ADD COLUMN server_ip VARCHAR(120) NULL,
ADD COLUMN server_port INTEGER NULL;

-- Add comment to document the new fields
COMMENT ON COLUMN rboxes.server_ip IS 'IP address of the video streaming server';
COMMENT ON COLUMN rboxes.server_port IS 'Port number of the video streaming server';
