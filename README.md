# Aquatic-Robotic-System

## Environment setup

It is strongly recommended to use a virtual environment for this project so dependencies stay isolated and consistent across machines.

### Create a virtual environment
```bash
python -m venv .venv
```

### Activate it
On Windows:
```bash
.venv\Scripts\activate
```

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run the simulation
```bash
python src/ui.py
```

### Run tests
```bash
python -m unittest -q tests.test_simulation
```

## SQLite database

The UI writes to `aquatic_sim.db` in the project root. The database contains only these three queryable data tables:

- `baseline`: exactly 100 randomly selected grid points with pH, turbidity, salinity, longitude, and latitude.
- `timeseries_data`: each robot reading with timestamp, coordinates, sensor values, composite `anomaly_index`, and the run's `anomaly_threshold`.
- `anomaly_data`: readings whose composite score is above the baseline threshold, with latitude, longitude, timestamp, and `anomaly_score`.

The composite index is calculated as `A = w1 * |ZpH| + w2 * |ZNTU| + w3 * |Zsalinity|`, using equal weights by default. Each Z-score uses the mean and standard deviation of the 100 baseline points. The anomaly threshold is the 95th percentile of the baseline composite scores.

Query the database with the SQLite CLI or any SQLite browser:

```sql
-- Baseline points
SELECT *
FROM baseline;

-- All time-series readings and scores
SELECT *
FROM timeseries_data
ORDER BY step, id;

-- Composite anomaly readings
SELECT recorded_at, latitude, longitude, anomaly_score
FROM anomaly_data
ORDER BY recorded_at, id;
```
