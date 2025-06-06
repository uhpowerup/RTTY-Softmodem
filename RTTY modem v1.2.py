import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import sounddevice as sd
import threading
import queue
import serial.tools.list_ports
import serial
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Constants for RTTY
FS = 44100
baud_rate = 45.45
BIT_LEN = int(FS / baud_rate)
MARK = 2125
SHIFT = 170
STOP_BITS = 2

# Baudot code mappings
baudot = {
    'A': 0b00011, 'B': 0b11001, 'C': 0b01110, 'D': 0b01001,
    'E': 0b00001, 'F': 0b01101, 'G': 0b11010, 'H': 0b10100,
    'I': 0b00110, 'J': 0b01011, 'K': 0b01111, 'L': 0b10010,
    'M': 0b11100, 'N': 0b01100, 'O': 0b11000, 'P': 0b10110,
    'Q': 0b10111, 'R': 0b01010, 'S': 0b00101, 'T': 0b10000,
    'U': 0b00111, 'V': 0b11110, 'W': 0b10011, 'X': 0b11101,
    'Y': 0b10101, 'Z': 0b10001, ' ': 0b00100
}
rev_baudot = {v: k for k, v in baudot.items()}

# Globals for devices and PTT
input_device = None
output_device = None
serial_port_name = None
ptt_serial = None
ptt_enabled = False

# Audio queues
rx_queue = queue.Queue()
fft_queue = queue.Queue()

# --- Helper functions for audio ---

def generate_tone(frequency, duration_sec, volume=0.5):
    t = np.arange(int(FS * duration_sec)) / FS
    return volume * np.sin(2 * np.pi * frequency * t)

def transmit_rtty(text, volume=0.5):
    global output_device
    bit_time = 1 / baud_rate
    stream = sd.OutputStream(samplerate=FS, device=output_device, channels=1)
    stream.start()

    def char_to_bits(c):
        val = baudot.get(c.upper(), 0)
        bits = [0]  # Start bit
        for i in range(5):
            bits.append((val >> i) & 1)
        for _ in range(STOP_BITS):
            bits.append(1)
        return bits

    for c in text:
        bits = char_to_bits(c)
        for bit in bits:
            freq = MARK if bit == 1 else MARK - SHIFT
            tone = generate_tone(freq, bit_time, volume)
            stream.write(tone.astype(np.float32))
    stream.stop()
    stream.close()

def rx_callback(indata, frames, time, status):
    if status:
        print(status)
    data = indata[:, 0].copy()
    rx_queue.put(data)
    # Calculate FFT for waterfall display
    fft = np.abs(np.fft.rfft(data * np.hamming(len(data))))
    fft_queue.put(fft[:512])

# RX decoding thread
def rx_process(rx_output_text, scroll_lock_var, status_var):
    buffer = np.array([])
    bit_len = BIT_LEN
    state = 'idle'
    bits = []
    sample_counter = 0
    while True:
        chunk = rx_queue.get()
        if chunk is None:
            break
        buffer = np.append(buffer, chunk)
        while len(buffer) >= bit_len:
            bit_chunk = buffer[:bit_len]
            buffer = buffer[bit_len:]
            # FFT analysis for bit detection
            fft = np.abs(np.fft.rfft(bit_chunk * np.hamming(len(bit_chunk))))
            freqs = np.fft.rfftfreq(len(bit_chunk), 1 / FS)
            mark_idx = np.argmin(np.abs(freqs - MARK))
            space_idx = np.argmin(np.abs(freqs - (MARK - SHIFT)))
            bit_val = 1 if fft[mark_idx] > fft[space_idx] else 0

            if state == 'idle':
                if bit_val == 0:  # start bit detected
                    bits = []
                    state = 'data'
                    sample_counter = 0
            elif state == 'data':
                bits.append(bit_val)
                sample_counter += 1
                if sample_counter == 5:
                    state = 'stop'
            elif state == 'stop':
                if bit_val == 1:  # stop bit must be 1
                    val = 0
                    for i, b in enumerate(bits):
                        val |= (b << i)
                    char = rev_baudot.get(val, '?')
                    def insert_char(c=char):
                        rx_output_text.insert('end', c)
                        if not scroll_lock_var.get():
                            rx_output_text.see('end')
                    rx_output_text.after(0, insert_char)
                state = 'idle'

# PTT control
def open_ptt_serial(port_name):
    global ptt_serial
    try:
        ptt_serial = serial.Serial(port_name, 9600)
    except Exception as e:
        messagebox.showerror("Serial Port Error", f"Failed to open {port_name}: {e}")
        ptt_serial = None

def set_ptt(state):
    global ptt_serial, ptt_enabled
    if ptt_enabled and ptt_serial and ptt_serial.is_open:
        try:
            ptt_serial.setRTS(state)
        except Exception as e:
            print("PTT error:", e)

class RTTYApp:
    def __init__(self, root):
        self.root = root
        root.title("RTTY Softmodem v1.2")

        self.tab_control = ttk.Notebook(root)
        self.tab_txrx = ttk.Frame(self.tab_control)
        self.tab_settings = ttk.Frame(self.tab_control)
        self.tab_about = ttk.Frame(self.tab_control)

        self.tab_control.add(self.tab_txrx, text='TX/RX')
        self.tab_control.add(self.tab_settings, text='Settings')
        self.tab_control.add(self.tab_about, text='About')
        self.tab_control.pack(expand=1, fill='both')

        # TX/RX tab
        self.tx_input = tk.Text(self.tab_txrx, height=5)
        self.tx_input.pack(fill='x', padx=5, pady=5)

        self.tx_button = ttk.Button(self.tab_txrx, text="Transmit", command=self.transmit)
        self.tx_button.pack(padx=5, pady=5)

        self.rx_output = tk.Text(self.tab_txrx, height=10)
        self.rx_output.pack(fill='both', expand=1, padx=5, pady=5)

        # Waterfall plot setup
        self.fig, self.ax = plt.subplots(figsize=(5, 2))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.tab_txrx)
        self.canvas.get_tk_widget().pack(fill='x', padx=5, pady=5)
        self.ax.set_title("FFT")
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, FS/2)
        self.waterfall_data = np.zeros((100, 512))
        self.im = self.ax.imshow(self.waterfall_data, aspect='auto', origin='lower',
                                 extent=[0, FS/2, 0, 100], cmap='inferno')

     # --- New frequency shift slider ---
        ttk.Label(self.tab_settings, text="Frequency Shift (50-500Hz):").grid(row=7, column=0, sticky='w', padx=5, pady=2)
        self.shift_var = tk.IntVar(value=SHIFT)
        self.shift_slider = ttk.Scale(self.tab_settings, from_=50, to=500, variable=self.shift_var, orient='horizontal')
        self.shift_slider.grid(row=7, column=1, sticky='ew', padx=5, pady=2)
        self.shift_slider.bind("<ButtonRelease-1>", self.on_shift_change)

        # Settings tab
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.serial_var = tk.StringVar()
        self.volume_var = tk.DoubleVar(value=0.5)
        self.scroll_lock_var = tk.BooleanVar(value=False)
        self.ptt_var = tk.BooleanVar(value=False)

        ttk.Label(self.tab_settings, text="Input Device:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.input_combo = ttk.Combobox(self.tab_settings, textvariable=self.input_var, state='readonly')
        self.input_combo.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        self.input_combo.bind("<<ComboboxSelected>>", self.on_input_device_change)

        ttk.Label(self.tab_settings, text="Output Device:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.output_combo = ttk.Combobox(self.tab_settings, textvariable=self.output_var, state='readonly')
        self.output_combo.grid(row=1, column=1, sticky='ew', padx=5, pady=2)
        self.output_combo.bind("<<ComboboxSelected>>", self.on_output_device_change)

        ttk.Label(self.tab_settings, text="Serial Port (PTT):").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        self.serial_combo = ttk.Combobox(self.tab_settings, textvariable=self.serial_var, state='readonly')
        self.serial_combo.grid(row=2, column=1, sticky='ew', padx=5, pady=2)
        self.serial_combo.bind("<<ComboboxSelected>>", self.on_serial_port_change)

        ttk.Checkbutton(self.tab_settings, text="Enable PTT", variable=self.ptt_var, command=self.on_ptt_toggle).grid(row=3, column=0, columnspan=2, sticky='w', padx=5, pady=2)

        ttk.Label(self.tab_settings, text="Volume:").grid(row=4, column=0, sticky='w', padx=5, pady=2)
        self.volume_slider = ttk.Scale(self.tab_settings, from_=0, to=1, variable=self.volume_var, orient='horizontal')
        self.volume_slider.grid(row=4, column=1, sticky='ew', padx=5, pady=2)

        ttk.Checkbutton(self.tab_settings, text="Scroll Lock RX", variable=self.scroll_lock_var).grid(row=5, column=0, columnspan=2, sticky='w', padx=5, pady=2)

        # --- New baud rate selector ---
        ttk.Label(self.tab_settings, text="Baud Rate:").grid(row=6, column=0, sticky='w', padx=5, pady=2)
        self.baud_rate_var = tk.DoubleVar(value=baud_rate)
        baud_rates = [45.45, 50, 75, 100, 110, 300]
        self.baud_rate_combo = ttk.Combobox(self.tab_settings, textvariable=self.baud_rate_var, state='readonly', values=baud_rates)
        self.baud_rate_combo.grid(row=6, column=1, sticky='ew', padx=5, pady=2)
        self.baud_rate_combo.bind("<<ComboboxSelected>>", self.on_baud_rate_change)


        # About tab content
        ttk.Label(self.tab_about, text="RTTY Softmodem v1.2\nBy 2E0UMR\n\nhttps://uhpowerup.com/\n\nSerial PTT: RTS\nPython + Tkinter + sounddevice + matplotlib + pyserial + Open AI").pack(padx=10, pady=10)

        self.update_device_lists()
        # Start audio input stream
        self.stream = None
        self.rx_thread = threading.Thread(target=rx_process, args=(self.rx_output, self.scroll_lock_var, None), daemon=True)
        self.rx_thread.start()
        self.start_rx_stream()
        self.update_waterfall()

    def update_device_lists(self):
        devices = sd.query_devices()
        input_devices = [d['name'] for d in devices if d['max_input_channels'] > 0]
        output_devices = [d['name'] for d in devices if d['max_output_channels'] > 0]
        self.input_combo['values'] = input_devices
        self.output_combo['values'] = output_devices
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.serial_combo['values'] = ports

    def on_input_device_change(self, event):
        global input_device
        input_device = self.input_var.get()
        self.restart_rx_stream()

    def on_output_device_change(self, event):
        global output_device
        output_device = self.output_var.get()

    def on_serial_port_change(self, event):
        global serial_port_name
        serial_port_name = self.serial_var.get()
        open_ptt_serial(serial_port_name)

    def on_ptt_toggle(self):
        global ptt_enabled
        ptt_enabled = self.ptt_var.get()

    def on_baud_rate_change(self, event):
        global baud_rate, BIT_LEN
        baud_rate = self.baud_rate_var.get()
        BIT_LEN = int(FS / baud_rate)
        print(f"Baud rate set to: {baud_rate} baud, BIT_LEN updated to {BIT_LEN}")

    def on_shift_change(self, event):
        global SHIFT
        SHIFT = int(self.shift_var.get())
        print(f"Frequency shift set to: {SHIFT} Hz")

    def start_rx_stream(self):
        global input_device
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if input_device is None:
            input_device = sd.default.device[0]
        self.stream = sd.InputStream(samplerate=FS, device=input_device, channels=1, callback=rx_callback)
        self.stream.start()

    def restart_rx_stream(self):
        self.start_rx_stream()

    def update_waterfall(self):
        # Pull all FFT data from queue and update waterfall
        updated = False
        try:
            while True:
                fft = fft_queue.get_nowait()
                self.waterfall_data = np.roll(self.waterfall_data, -1, axis=0)
                self.waterfall_data[-1, :] = fft
                updated = True
        except queue.Empty:
            pass
        if updated:
            self.im.set_data(self.waterfall_data)
            self.im.set_clim(np.min(self.waterfall_data), np.max(self.waterfall_data))
            self.canvas.draw()
        self.root.after(100, self.update_waterfall)

    def transmit(self):
        text = self.tx_input.get("1.0", "end").strip()
        if not text:
            return
        set_ptt(True)
        threading.Thread(target=self._transmit_thread, args=(text,), daemon=True).start()

    def _transmit_thread(self, text):
        transmit_rtty(text, volume=self.volume_var.get())
        set_ptt(False)

def main():
    root = tk.Tk()
    app = RTTYApp(root)
    root.mainloop()

if __name__ == '__main__':
    root = tk.Tk()
    app = RTTYApp(root)
    root.mainloop()
