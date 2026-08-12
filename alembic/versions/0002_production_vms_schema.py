"""Production VMS Architecture Schema (Events, Journeys, Audio, Health, Forensics, Copilot, Rules, Skills)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create Canonical Events Table
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('event_uuid', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('deduplication_key', sa.String(), index=True, nullable=False),
        sa.Column('parent_event_id', sa.String(), index=True, nullable=True),
        sa.Column('source_event_ids_json', sa.Text(), server_default='[]', nullable=False),
        sa.Column('organization_id', sa.String(), server_default='org_default', index=True, nullable=False),
        sa.Column('site_id', sa.String(), server_default='site_main', index=True, nullable=False),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('event_type', sa.String(), index=True, nullable=False),
        sa.Column('source_type', sa.String(), index=True, server_default='video'),
        sa.Column('source_component', sa.String(), server_default='ai_pipeline'),
        sa.Column('status', sa.String(), server_default='DETECTED', index=True, nullable=False),
        sa.Column('severity', sa.String(), server_default='medium', index=True, nullable=False),
        sa.Column('confidence', sa.Float(), server_default='0.95', index=True, nullable=False),
        sa.Column('track_id', sa.String(), index=True, nullable=True),
        sa.Column('global_identity_id', sa.String(), index=True, nullable=True),
        sa.Column('metadata_json', sa.Text(), server_default='{}', nullable=False),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('model_version', sa.String(), nullable=True),
        sa.Column('inference_backend', sa.String(), nullable=True),
        sa.Column('snapshot_url', sa.String(), nullable=True),
        sa.Column('video_url', sa.String(), nullable=True),
        sa.Column('evidence_refs_json', sa.Text(), server_default='[]', nullable=False),
        sa.Column('timestamp_start', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('timestamp_end', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('is_acknowledged', sa.Boolean(), server_default='0', index=True)
    )

    # 2. Create Person Journey Events Table
    op.create_table(
        'person_journey_events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('global_person_id', sa.String(), index=True, nullable=False),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('track_id', sa.String(), index=True, nullable=True),
        sa.Column('timestamp_start', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('timestamp_end', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('confidence', sa.Float(), server_default='0.0', index=True, nullable=False),
        sa.Column('embedding_ref', sa.String(), nullable=True),
        sa.Column('transition_from_camera', sa.String(), nullable=True),
        sa.Column('transition_to_camera', sa.String(), nullable=True),
        sa.Column('snapshot_url', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(), server_default='org_default', index=True, nullable=False),
        sa.Column('site_id', sa.String(), server_default='site_main', index=True, nullable=False)
    )

    # 3. Create Vehicle Journey Events Table
    op.create_table(
        'vehicle_journey_events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('global_vehicle_id', sa.String(), index=True, nullable=False),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('track_id', sa.String(), index=True, nullable=True),
        sa.Column('license_plate', sa.String(), index=True, nullable=True),
        sa.Column('timestamp_start', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('timestamp_end', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('confidence', sa.Float(), server_default='0.0', index=True, nullable=False),
        sa.Column('embedding_ref', sa.String(), nullable=True),
        sa.Column('transition_from_camera', sa.String(), nullable=True),
        sa.Column('transition_to_camera', sa.String(), nullable=True),
        sa.Column('snapshot_url', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(), server_default='org_default', index=True, nullable=False),
        sa.Column('site_id', sa.String(), server_default='site_main', index=True, nullable=False)
    )

    # 4. Create Audio Events Table
    op.create_table(
        'audio_events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('event_uuid', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('duration_seconds', sa.Float(), server_default='1.0'),
        sa.Column('event_type', sa.String(), index=True, nullable=False),
        sa.Column('is_anomaly', sa.Boolean(), server_default='1', index=True),
        sa.Column('classifier_name', sa.String(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('model_version', sa.String(), nullable=True),
        sa.Column('confidence', sa.Float(), server_default='0.0', index=True),
        sa.Column('anomaly_score', sa.Float(), server_default='0.0'),
        sa.Column('decibels', sa.Float(), server_default='0.0'),
        sa.Column('peak_frequency_hz', sa.Float(), server_default='0.0'),
        sa.Column('audio_features_json', sa.Text(), server_default='{}', nullable=False),
        sa.Column('evidence_ref', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(), server_default='org_default', index=True, nullable=False),
        sa.Column('site_id', sa.String(), server_default='site_main', index=True, nullable=False)
    )

    # 5. Create Camera Topologies Table
    op.create_table(
        'camera_topologies',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('from_camera_id', sa.String(), index=True, nullable=False),
        sa.Column('to_camera_id', sa.String(), index=True, nullable=False),
        sa.Column('min_travel_seconds', sa.Float(), server_default='5.0'),
        sa.Column('max_travel_seconds', sa.Float(), server_default='1800.0'),
        sa.Column('distance_meters', sa.Float(), server_default='50.0')
    )

    # 6. Create Camera Health Logs Table
    op.create_table(
        'camera_health_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('status', sa.String(), server_default='ONLINE', index=True),
        sa.Column('fps', sa.Float(), server_default='0.0'),
        sa.Column('bitrate_kbps', sa.Float(), server_default='0.0'),
        sa.Column('latency_ms', sa.Float(), server_default='0.0'),
        sa.Column('reconnect_count', sa.Integer(), server_default='0'),
        sa.Column('freeze_score', sa.Float(), server_default='0.0'),
        sa.Column('dark_score', sa.Float(), server_default='0.0'),
        sa.Column('blur_score', sa.Float(), server_default='0.0'),
        sa.Column('obscure_score', sa.Float(), server_default='0.0'),
        sa.Column('movement_score', sa.Float(), server_default='0.0')
    )

    # 7. Create Camera Baselines Table
    op.create_table(
        'camera_baselines',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('hour_of_day', sa.Integer(), index=True, nullable=False),
        sa.Column('avg_count', sa.Float(), server_default='0.0'),
        sa.Column('std_dev', sa.Float(), server_default='1.0'),
        sa.Column('min_count', sa.Integer(), server_default='0'),
        sa.Column('max_count', sa.Integer(), server_default='0'),
        sa.Column('sample_count', sa.Integer(), server_default='0')
    )

    # 8. Create Investigations Table
    op.create_table(
        'investigations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('investigation_uuid', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('username', sa.String(), index=True, nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('time_range_json', sa.Text(), server_default='{}', nullable=False),
        sa.Column('camera_ids_json', sa.Text(), server_default='[]', nullable=False),
        sa.Column('tool_calls_json', sa.Text(), server_default='[]', nullable=False),
        sa.Column('returned_event_ids_json', sa.Text(), server_default='[]', nullable=False),
        sa.Column('final_answer', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), index=True)
    )

    # 9. Create Evidence Ledger & Chain of Custody Tables
    op.create_table(
        'evidence_ledger',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('evidence_uuid', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sha256_hash', sa.String(), index=True, nullable=False),
        sa.Column('manifest_signature', sa.Text(), nullable=True),
        sa.Column('creator_username', sa.String(), index=True, nullable=False),
        sa.Column('original_file_path', sa.String(), nullable=False),
        sa.Column('redacted_file_path', sa.String(), nullable=True),
        sa.Column('is_protected', sa.Boolean(), server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), index=True)
    )

    op.create_table(
        'evidence_chain_of_custody',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('evidence_uuid', sa.String(), index=True, nullable=False),
        sa.Column('username', sa.String(), index=True, nullable=False),
        sa.Column('action', sa.String(), index=True, nullable=False),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), index=True),
        sa.Column('reason_comment', sa.Text(), nullable=True)
    )

    # 10. Create AI Skill Registry & Assignment Tables
    op.create_table(
        'ai_skills_registry',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('skill_id', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('input_type', sa.String(), server_default='frame'),
        sa.Column('output_schema_json', sa.Text(), server_default='{}', nullable=False),
        sa.Column('hardware_req', sa.String(), server_default='CPU'),
        sa.Column('min_fps', sa.Float(), server_default='1.0'),
        sa.Column('target_fps', sa.Float(), server_default='5.0'),
        sa.Column('max_fps', sa.Float(), server_default='10.0'),
        sa.Column('is_enabled', sa.Boolean(), server_default='1')
    )

    op.create_table(
        'camera_skill_assignments',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('camera_id', sa.String(), index=True, nullable=False),
        sa.Column('skill_id', sa.String(), index=True, nullable=False),
        sa.Column('config_json', sa.Text(), server_default='{}', nullable=False)
    )

    # 11. Create Event Rules Table
    op.create_table(
        'event_rules',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('rule_id', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('conditions_json', sa.Text(), nullable=False),
        sa.Column('actions_json', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(), server_default='high'),
        sa.Column('cooldown_seconds', sa.Integer(), server_default='60'),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('organization_id', sa.String(), server_default='org_default', index=True, nullable=False),
        sa.Column('site_id', sa.String(), server_default='site_main', index=True, nullable=False)
    )


def downgrade() -> None:
    op.drop_table('event_rules')
    op.drop_table('camera_skill_assignments')
    op.drop_table('ai_skills_registry')
    op.drop_table('evidence_chain_of_custody')
    op.drop_table('evidence_ledger')
    op.drop_table('investigations')
    op.drop_table('camera_baselines')
    op.drop_table('camera_health_logs')
    op.drop_table('camera_topologies')
    op.drop_table('audio_events')
    op.drop_table('vehicle_journey_events')
    op.drop_table('person_journey_events')
    op.drop_table('events')
