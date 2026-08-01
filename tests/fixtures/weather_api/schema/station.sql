CREATE TABLE station (
  id SERIAL PRIMARY KEY,
  callsign TEXT NOT NULL,
  latitude NUMERIC(9,6) NOT NULL,
  longitude NUMERIC(9,6) NOT NULL,
  elevation_m INTEGER,
  last_reading_at TIMESTAMPTZ
);

CREATE TABLE reading (
  id BIGSERIAL PRIMARY KEY,
  station_id INTEGER REFERENCES station(id),
  temperature_c NUMERIC(4,1),
  ip_address INET,
  recorded_at TIMESTAMPTZ NOT NULL
);
