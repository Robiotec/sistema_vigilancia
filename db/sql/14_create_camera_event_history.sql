CREATE TABLE IF NOT EXISTS camera_event_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    event_type varchar(32) NOT NULL,
    event_category varchar(64),
    origin varchar(32) NOT NULL DEFAULT 'fixed_camera',

    camera_id varchar(128) NOT NULL,
    camera_name varchar(160),
    camera_location text,

    event_timestamp bigint,
    detected_at timestamptz NOT NULL,
    detected_date date,

    title text NOT NULL,
    description text,

    person_id varchar(64),
    person_name text,
    plate varchar(32),
    track_id integer,

    status varchar(32) NOT NULL DEFAULT 'new',
    severity varchar(32),

    manifest_file_path text,
    json_file_path text,
    video_file_path text,
    image_file_path text,
    crop_path text,

    manifest_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    detail_payload jsonb NOT NULL DEFAULT '{}'::jsonb,

    event_uid text GENERATED ALWAYS AS (
        md5(
            coalesce(camera_id, '') || '|' ||
            coalesce(event_type, '') || '|' ||
            coalesce(event_timestamp::text, '') || '|' ||
            coalesce(track_id::text, '') || '|' ||
            coalesce(person_id, '') || '|' ||
            coalesce(plate, '') || '|' ||
            coalesce(json_file_path, '') || '|' ||
            coalesce(video_file_path, '') || '|' ||
            coalesce(image_file_path, '') || '|' ||
            coalesce(crop_path, '') || '|' ||
            coalesce(manifest_file_path, '')
        )
    ) STORED,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_camera_event_history_origin
        CHECK (origin IN ('fixed_camera', 'vehicle', 'drone', 'system')),
    CONSTRAINT ck_camera_event_history_status
        CHECK (status IN ('new', 'reviewed', 'archived', 'dismissed')),
    CONSTRAINT ck_camera_event_history_severity
        CHECK (severity IS NULL OR severity IN ('info', 'warning', 'critical')),
    CONSTRAINT uq_camera_event_history_event_uid UNIQUE (event_uid)
);

CREATE INDEX IF NOT EXISTS idx_camera_event_history_detected_at
    ON camera_event_history (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_camera_event_history_camera_time
    ON camera_event_history (camera_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_camera_event_history_camera_name_time
    ON camera_event_history (camera_name, detected_at DESC)
    WHERE camera_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_camera_event_history_type_time
    ON camera_event_history (event_type, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_camera_event_history_category_time
    ON camera_event_history (event_category, detected_at DESC)
    WHERE event_category IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_camera_event_history_origin_time
    ON camera_event_history (origin, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_camera_event_history_status_time
    ON camera_event_history (status, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_camera_event_history_person_id
    ON camera_event_history (person_id)
    WHERE person_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_camera_event_history_plate
    ON camera_event_history (plate)
    WHERE plate IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_camera_event_history_detail_payload
    ON camera_event_history USING gin (detail_payload);

GRANT SELECT, INSERT, UPDATE, DELETE ON camera_event_history TO robiotec_app;
