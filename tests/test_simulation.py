import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulation import SimulationEngine


class SimulationEngineTests(unittest.TestCase):
    def test_database_contains_only_requested_tables(self):
        engine = SimulationEngine(width=10, height=10, cell_size=1, db_path=':memory:')
        tables = {
            row[0]
            for row in engine.db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        self.assertEqual(tables, {"baseline", "timeseries_data", "anomaly_data"})

    def test_step_updates_robot_and_persists_sample(self):
        engine = SimulationEngine(width=10, height=10, cell_size=1, db_path=':memory:')
        engine.start_run("test-run")

        before = engine.robot.position
        engine.step()

        self.assertNotEqual(engine.robot.position, before)
        self.assertGreaterEqual(len(engine.robot.history), 1)
        self.assertEqual(
            engine.db.conn.execute("SELECT COUNT(*) FROM timeseries_data").fetchone()[0],
            1,
        )

    def test_baseline_and_composite_timeseries_are_queryable(self):
        engine = SimulationEngine(width=10, height=10, cell_size=1, db_path=':memory:')
        engine.start_run("baseline-test")

        baseline_count = engine.db.conn.execute(
            "SELECT COUNT(*) FROM baseline"
        ).fetchone()[0]
        self.assertEqual(baseline_count, 100)
        self.assertIsNotNone(engine.anomaly_threshold)

        engine.step()
        row = engine.db.conn.execute(
            """SELECT ph, turbidity, salinity, longitude, latitude,
                      anomaly_index, anomaly_threshold
               FROM timeseries_data""",
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(len(row), 7)
        self.assertGreaterEqual(row[5], 0.0)

    def test_reading_above_threshold_is_saved_as_anomaly(self):
        engine = SimulationEngine(width=10, height=10, cell_size=1, db_path=':memory:')
        engine.start_run("anomaly-test")
        engine.grid[1][1] = {"ph": 2.0, "turbidity": 100.0, "salinity": 10.0}

        engine.step()

        anomaly = engine.db.conn.execute(
            "SELECT latitude, longitude, anomaly_score FROM anomaly_data"
        ).fetchone()
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly[0], engine.ORIGIN_LATITUDE + engine.CELL_DEGREES)
        self.assertEqual(anomaly[1], engine.ORIGIN_LONGITUDE + engine.CELL_DEGREES)
        self.assertGreater(anomaly[2], engine.anomaly_threshold)


if __name__ == '__main__':
    unittest.main()
