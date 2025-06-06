# RTTY Softmodem for Windows/Linux

![RTTY softmodem](https://github.com/user-attachments/assets/7a6acdb9-3a05-4115-b26b-34869310b260)

This is a simple real-time RTTY (Radio Teletype) software modem application written in Python. It supports receiving and transmitting Baudot-coded RTTY signals using your computer's sound card and optionally controls PTT via serial port RTS line.

---

## Features

- Real-time RTTY reception with Baudot decoding (basic letters and space)
- RTTY transmission with selectable text input
- Audio input/output device selection
- Waterfall FFT display for signal visualization
- Serial RTS-based PTT control for transmitting (configurable serial port)
- Scroll lock option for RX text window
- Configurable baud rate 
- Frequancy Shift (50-500HZ)
- Multi-threaded design for responsive GUI

---
## Requirements

- Python 3.7+
- [numpy](https://numpy.org/)
- [sounddevice](https://python-sounddevice.readthedocs.io/en/0.4.6/)
- [pyserial](https://pyserial.readthedocs.io/en/latest/)
- [matplotlib](https://matplotlib.org/)
- Tkinter (usually included with Python)
- [pyinstaller](https://pyinstaller.org/en/stable/)
  

---
##For Windows Executable: 
```bash
pyinstaller --onefile --windowed --icon=RTTY modem.ico --name=RTTY modem v1.2.py

```
##For linux

```bash
python RTTY Softmodem v1.2

```

Install dependencies via pip:

```bash
pip install pyinstaller numpy sounddevice pyserial matplotlib

```
##License
- MIT License — feel free to use and modify for your amateur radio projects!

##Acknowledgments
- Inspired by classic RTTY decoding methods and amateur radio software modem designs.


