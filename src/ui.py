import math
import tkinter as tk
from tkinter import ttk
from simulation import SimulationEngine


class SimulationUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Aqua Bot | Water Quality Monitor")
        self.root.configure(bg='#e7f7fb')
        self.engine = SimulationEngine(width=12, height=12, cell_size=1, db_path='aquatic_sim.db')
        self.engine.start_run("demo-run")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(root, width=520, height=520, bg='#0b5574', highlightthickness=0)
        self.canvas.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(16, 8), pady=16)

        self.control_frame = tk.Frame(root, bg='#e7f7fb', padx=12, pady=16)
        self.control_frame.grid(row=0, column=1, sticky='new', padx=(8, 16), pady=16)

        tk.Label(
            self.control_frame, text='AQUA BOT', font=('Segoe UI', 20, 'bold'),
            fg='#06445f', bg='#e7f7fb'
        ).grid(row=0, column=0, columnspan=2, sticky='w')
        tk.Label(
            self.control_frame, text='Live water quality patrol', font=('Segoe UI', 10),
            fg='#477785', bg='#e7f7fb'
        ).grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 18))

        button_style = {
            'font': ('Segoe UI', 10, 'bold'), 'fg': 'white', 'activeforeground': 'white',
            'activebackground': '#087f9f', 'relief': 'flat', 'bd': 0, 'padx': 16, 'pady': 9,
        }
        self.start_button = tk.Button(self.control_frame, text='Start', bg='#087f9f', command=self._start_loop, **button_style)
        self.start_button.grid(row=2, column=0, padx=(0, 6), sticky='ew')
        self.pause_button = tk.Button(self.control_frame, text='Pause', bg='#155f7a', command=self._pause_loop, **button_style)
        self.pause_button.grid(row=2, column=1, padx=(6, 0), sticky='ew')
        self.control_frame.columnconfigure(0, weight=1)
        self.control_frame.columnconfigure(1, weight=1)

        self.info = tk.Label(
            self.control_frame, text='', wraplength=300, justify=tk.LEFT, anchor='nw',
            font=('Segoe UI', 10), fg='#164d60', bg='#d5f0f5',
            padx=14, pady=14, relief='flat'
        )
        self.info.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(14, 0))

        self.running = False
        self.after_id = None
        self._draw()

    def _draw(self):
        self.canvas.delete("all")
        size = 40

        for y in range(self.engine.height):
            for x in range(self.engine.width):
                cell = self.engine.read_cell(x, y)
                color = self._heat_color(cell)
                self.canvas.create_rectangle(x * size, y * size, (x + 1) * size, (y + 1) * size, fill=color, outline='#79c5d4', width=1)

        history_points = [(item['x'] * size, item['y'] * size) for item in self.engine.robot.history[-30:]]
        for i in range(len(history_points) - 1):
            self.canvas.create_line(*history_points[i], *history_points[i + 1], fill='orange', width=3)
        for x, y in history_points:
            self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill='gold', outline='')

        px, py = self.engine.robot.position
        self.canvas.create_oval(px * size - 8, py * size - 8, px * size + 8, py * size + 8, fill='#18a558', outline='#075e2f', width=2)
        heading_x = px * size + math.cos(math.radians(self.engine.robot.heading)) * 20
        heading_y = py * size + math.sin(math.radians(self.engine.robot.heading)) * 20
        self.canvas.create_line(px * size, py * size, heading_x, heading_y, fill='black', width=2, arrow=tk.LAST)
        self.canvas.create_text(px * size, py * size - 16, text=self.engine.robot.mode, fill='black', font=('Arial', 9, 'bold'))

        sample = self.engine.robot.history[-1] if self.engine.robot.history else None
        if sample:
            self.info.config(text=(
                f"STATUS   {sample['mode']}\n\n"
                f"Position: ({sample['x']:.2f}, {sample['y']:.2f})\n"
                f"Heading: {sample['heading']:.1f}°\n"
                f"Velocity dx/dy: ({sample['dx']:.2f}, {sample['dy']:.2f})\n"
                f"pH: {sample['ph']:.2f} (mean {sample['ph_mean']:.2f}, median {sample['ph_median']:.2f})\n"
                f"Turbidity: {sample['turbidity']:.2f} (mean {sample['turb_mean']:.2f}, median {sample['turb_median']:.2f})\n"
                f"Salinity: {sample['salinity']:.2f} (mean {sample['sal_mean']:.2f}, median {sample['sal_median']:.2f})\n"
                f"Composite anomaly: {sample['anomaly_index']:.2f}\n"
                f"Threshold: {sample['anomaly_threshold']:.2f}"
            ))

    def _heat_color(self, cell):
        turbidity = max(0.0, min(1.0, (cell['turbidity'] - 10.0) / 12.0))
        start = (20, 111, 145)
        end = (83, 194, 211)
        red = int(start[0] + (end[0] - start[0]) * (1 - turbidity))
        green = int(start[1] + (end[1] - start[1]) * (1 - turbidity))
        blue = int(start[2] + (end[2] - start[2]) * (1 - turbidity))
        return f'#{red:02x}{green:02x}{blue:02x}'

    def _step(self):
        self.engine.step()
        self._draw()
        if self.running:
            self.after_id = self.root.after(150, self._step)

    def _start_loop(self):
        if not self.running:
            self.running = True
            self._step()

    def _pause_loop(self):
        if self.running and self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
            self.running = False


if __name__ == '__main__':
    root = tk.Tk()
    app = SimulationUI(root)
    root.mainloop()
