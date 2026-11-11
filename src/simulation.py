import math
import random
import sqlite3
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Robot:
    position: Tuple[float, float]
    velocity: Tuple[float, float] = (0.0, 0.0)
    heading: float = 0.0
    mode: str = "Patrolling"
    history: List[dict] = field(default_factory=list)


class SQLiteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        for view in ("time_series", "cell_time_series"):
            cur.execute(f"DROP VIEW IF EXISTS {view}")
        for table in ("runs", "samples", "cell_data", "anomalies", "remediation_events"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("PRAGMA table_info(baseline)")
        if any(row[1] == "run_id" for row in cur.fetchall()):
            cur.execute("DROP TABLE IF EXISTS anomaly_data")
            cur.execute("DROP TABLE IF EXISTS timeseries_data")
            cur.execute("DROP TABLE IF EXISTS baseline")
        cur.execute('''
            CREATE TABLE IF NOT EXISTS baseline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ph REAL NOT NULL,
                turbidity REAL NOT NULL,
                salinity REAL NOT NULL,
                longitude REAL NOT NULL,
                latitude REAL NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS timeseries_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                step INTEGER NOT NULL,
                ph REAL NOT NULL,
                turbidity REAL NOT NULL,
                salinity REAL NOT NULL,
                longitude REAL NOT NULL,
                latitude REAL NOT NULL,
                anomaly_index REAL NOT NULL,
                anomaly_threshold REAL NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS anomaly_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timeseries_id INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                anomaly_score REAL NOT NULL,
                FOREIGN KEY(timeseries_id) REFERENCES timeseries_data(id)
            )
        ''')
        self.conn.commit()

    def save_baseline(self, rows: List[Tuple[float, float, float, float, float]]):
        self.conn.executemany(
            """INSERT INTO baseline(
                ph, turbidity, salinity, longitude, latitude
            ) VALUES(?, ?, ?, ?, ?)""",
            [(ph, turbidity, salinity, longitude, latitude)
             for ph, turbidity, salinity, longitude, latitude in rows],
        )
        self.conn.commit()

    def save_timeseries_data(
        self,
        step: int,
        ph: float,
        turbidity: float,
        salinity: float,
        longitude: float,
        latitude: float,
        anomaly_index: float,
        anomaly_threshold: float,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO timeseries_data(
                recorded_at, step, ph, turbidity, salinity,
                longitude, latitude, anomaly_index, anomaly_threshold
            ) VALUES(datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)""",
            (step, ph, turbidity, salinity, longitude, latitude,
             anomaly_index, anomaly_threshold),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def save_composite_anomaly(self, timeseries_id: int, latitude: float, longitude: float, anomaly_score: float):
        self.conn.execute(
            """INSERT INTO anomaly_data(
                timeseries_id, recorded_at, latitude, longitude, anomaly_score
            ) VALUES(?, datetime('now'), ?, ?, ?)""",
            (timeseries_id, latitude, longitude, anomaly_score),
        )
        self.conn.commit()


class SimulationEngine:
    PH_LOW_THRESHOLD = 6.5
    PH_HIGH_THRESHOLD = 8.0
    TURBIDITY_THRESHOLD = 18.0
    SALINITY_THRESHOLD = 1.2
    ORIGIN_LATITUDE = 12.9716
    ORIGIN_LONGITUDE = 77.5946
    CELL_DEGREES = 0.0001
    BASELINE_SAMPLE_SIZE = 100
    ANOMALY_WEIGHTS = (1 / 3, 1 / 3, 1 / 3)
    MAX_MOVEMENT_SPEED = 1.5
    RANDOM_MOVEMENT_RANGE = 0.5

    def __init__(self, width: int, height: int, cell_size: int, db_path: str):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.db = SQLiteStore(db_path)
        self.run_id = None
        self.step_count = 0
        self.robot = Robot(position=(1.0, 1.0))
        self.grid = self._build_grid(width, height)
        self.stuck_count = 0
        self.baseline_stats = None
        self.anomaly_threshold = None

    def _build_grid(self, width: int, height: int) -> List[List[dict]]:
        grid = []
        for y in range(height):
            row = []
            for x in range(width):
                base_ph = 7.2
                base_turbidity = 12.0
                base_salinity = 0.8
                if (x, y) == (5, 5):
                    base_ph -= 0.8
                    base_turbidity += 9.0
                elif (x, y) == (2, 7):
                    base_ph += 0.6
                    base_turbidity += 4.0
                row.append({
                    "ph": base_ph + random.uniform(-0.05, 0.05),
                    "turbidity": base_turbidity + random.uniform(-0.5, 0.5),
                    "salinity": base_salinity + random.uniform(-0.02, 0.02),
                })
            grid.append(row)
        return grid

    def start_run(self, name: str):
        self.run_id = name
        self.step_count = 0
        self._create_baseline()

    def _create_baseline(self):
        points = [(x, y) for y in range(self.height) for x in range(self.width)]
        selected = random.choices(points, k=self.BASELINE_SAMPLE_SIZE)
        rows = []
        for cell_x, cell_y in selected:
            cell = self.grid[cell_y][cell_x]
            latitude, longitude = self.coordinate_for(cell_x, cell_y)
            rows.append((cell["ph"], cell["turbidity"], cell["salinity"], longitude, latitude))
        self.db.save_baseline(rows)

        values = {
            "ph": [row[0] for row in rows],
            "turbidity": [row[1] for row in rows],
            "salinity": [row[2] for row in rows],
        }
        self.baseline_stats = {name: self._compute_stats(items) for name, items in values.items()}
        baseline_scores = [self.composite_anomaly_index(**dict(zip(values, sample))) for sample in zip(*values.values())]
        self.anomaly_threshold = self._percentile(baseline_scores, 95)

    @staticmethod
    def _percentile(values: List[float], percentile: float) -> float:
        ordered = sorted(values)
        position = (len(ordered) - 1) * percentile / 100
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    def coordinate_for(self, cell_x: int, cell_y: int) -> Tuple[float, float]:
        return (
            self.ORIGIN_LATITUDE + cell_y * self.CELL_DEGREES,
            self.ORIGIN_LONGITUDE + cell_x * self.CELL_DEGREES,
        )

    def composite_anomaly_index(self, ph: float, turbidity: float, salinity: float) -> float:
        if self.baseline_stats is None:
            raise RuntimeError("Baseline not initialized")
        z_scores = []
        for name, value in (("ph", ph), ("turbidity", turbidity), ("salinity", salinity)):
            stats = self.baseline_stats[name]
            z_scores.append(abs(value - stats["mean"]) / max(stats["std"], 1e-9))
        return sum(weight * score for weight, score in zip(self.ANOMALY_WEIGHTS, z_scores))

    def read_cell(self, x: int, y: int) -> dict:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return {"ph": 7.2, "turbidity": 12.0, "salinity": 0.8}
        return self.grid[y][x]

    def _compute_stats(self, values: List[float]) -> dict:
        values = sorted(values)
        n = len(values)
        mean = sum(values) / n if n else 0.0
        median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
        variance = sum((v - mean) ** 2 for v in values) / n if n else 0.0
        std = math.sqrt(variance)
        return {"mean": mean, "median": median, "std": std}

    def _compute_grid_stats(self) -> dict:
        all_ph = [cell["ph"] for row in self.grid for cell in row]
        all_turbidity = [cell["turbidity"] for row in self.grid for cell in row]
        all_salinity = [cell["salinity"] for row in self.grid for cell in row]
        return {
            "ph": self._compute_stats(all_ph),
            "turbidity": self._compute_stats(all_turbidity),
            "salinity": self._compute_stats(all_salinity),
        }

    def _compute_all_stats(self) -> dict:
        ph_values = [item["ph"] for item in self.robot.history[-20:]]
        turbidity_values = [item["turbidity"] for item in self.robot.history[-20:]]
        salinity_values = [item["salinity"] for item in self.robot.history[-20:]]
        return {
            "ph": self._compute_stats(ph_values),
            "turbidity": self._compute_stats(turbidity_values),
            "salinity": self._compute_stats(salinity_values),
        }

    def _movement_vector(self, ph: float, turbidity: float, salinity: float, stats: dict) -> Tuple[float, float]:
        dx = (stats["ph"]["mean"] - ph) * 0.7 + (stats["salinity"]["mean"] - salinity) * 0.22
        dy = (turbidity - stats["turbidity"]["mean"]) * 0.22 + (salinity - stats["salinity"]["mean"]) * 0.12
        speed = math.hypot(dx, dy)
        max_speed = self.MAX_MOVEMENT_SPEED
        if speed > max_speed:
            scale = max_speed / speed
            dx *= scale
            dy *= scale
        return dx, dy

    def _update_mode(self, ph: float, turbidity: float, z_score: float):
        if abs(z_score) > 2.5 or turbidity > 18.0:
            self.robot.mode = "Investigating"
        elif abs(z_score) > 1.5:
            self.robot.mode = "Anomaly"
        else:
            self.robot.mode = "Patrolling"

    def step(self):
        if self.run_id is None:
            raise RuntimeError("Run not started")

        x, y = self.robot.position
        cell_x = int(round(x))
        cell_y = int(round(y))
        cell = self.read_cell(cell_x, cell_y)

        ph = cell["ph"]
        turbidity = cell["turbidity"]
        salinity = cell["salinity"]

        stats = self._compute_all_stats() if self.robot.history else self._compute_grid_stats()
        z_score = (ph - stats["ph"]["mean"]) / max(0.1, stats["ph"]["std"])

        self._update_mode(ph, turbidity, z_score)

        dx, dy = self._movement_vector(ph, turbidity, salinity, stats)
        if abs(dx) < 0.15 and abs(dy) < 0.15:
            dx += random.uniform(-self.RANDOM_MOVEMENT_RANGE, self.RANDOM_MOVEMENT_RANGE)
            dy += random.uniform(-self.RANDOM_MOVEMENT_RANGE, self.RANDOM_MOVEMENT_RANGE)
        self.robot.velocity = (dx, dy)
        self.robot.heading = math.degrees(math.atan2(dy, dx))

        new_x = x + dx
        new_y = y + dy
        if new_x <= 0.0 or new_x >= self.width - 1:
            dx = -dx
            new_x = x + dx
        if new_y <= 0.0 or new_y >= self.height - 1:
            dy = -dy
            new_y = y + dy
        new_x = max(0.0, min(self.width - 1, new_x))
        new_y = max(0.0, min(self.height - 1, new_y))
        self.robot.position = (new_x, new_y)
        self.robot.velocity = (dx, dy)
        self.robot.heading = math.degrees(math.atan2(dy, dx))

        sample = {
            "step": self.step_count,
            "x": new_x,
            "y": new_y,
            "ph": ph,
            "turbidity": turbidity,
            "salinity": salinity,
            "mode": self.robot.mode,
            "z_score": z_score,
            "dx": dx,
            "dy": dy,
            "heading": self.robot.heading,
            "ph_mean": stats["ph"]["mean"],
            "ph_median": stats["ph"]["median"],
            "ph_std": stats["ph"]["std"],
            "turb_mean": stats["turbidity"]["mean"],
            "turb_median": stats["turbidity"]["median"],
            "sal_mean": stats["salinity"]["mean"],
            "sal_median": stats["salinity"]["median"],
        }
        self.robot.history.append(sample)
        latitude, longitude = self.coordinate_for(cell_x, cell_y)
        anomaly_index = self.composite_anomaly_index(ph, turbidity, salinity)
        sample["anomaly_index"] = anomaly_index
        sample["anomaly_threshold"] = self.anomaly_threshold
        timeseries_id = self.db.save_timeseries_data(
            self.step_count, ph, turbidity, salinity,
            longitude, latitude, anomaly_index, self.anomaly_threshold,
        )
        if anomaly_index > self.anomaly_threshold:
            self.db.save_composite_anomaly(timeseries_id, latitude, longitude, anomaly_index)
        self.step_count += 1
        return sample
