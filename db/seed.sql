insert into inference_entities (
    entity_id,
    entity_type,
    display_name,
    metadata
) values (
    'demo-demand-series',
    'time_series',
    'Demo Demand Forecast Series',
    '{"domain":"prototype","source":"seed"}'
);

commit;

