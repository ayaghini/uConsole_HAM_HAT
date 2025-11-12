# uConsole HAM Radio HAT

[![Status](https://img.shields.io/badge/status-prototype-yellow.svg)](https://github.com/ayaghini/uconsole-ham-hat)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Hardware](https://img.shields.io/badge/hardware-rev_1.0-green.svg)](hardware/)
[![Made for](https://img.shields.io/badge/platform-uConsole-red.svg)](https://clockworkpi.com/pages/uconsole)

---

The **uConsole HAM Radio HAT** is a dedicated expansion board designed for **ham radio operators**.  
It enables full **digital mode operation** (receive and transmit) on the **2-meter band** using an **SA818 transceiver module**, providing both **audio** and **serial control** paths.

---

## ✳️ Features

- **Integrated sound modem** for digital mode operation  
- **PTT and serial control** interface for SA818 module  
- **Dedicated audio and serial ports** — fully compatible with **Digirig cables and configurations**  
- **10/100 Ethernet interface** for network connectivity  
- **Dual connectivity options**:
  - Direct connection to the **uConsole AIO extension** via internal 4-pin pads  
  - External connection via **USB-C** port (works as a standalone portable device)
- Clean power and ground isolation design for low noise operation

---

## 🔧 Usage

The HAT can operate either:
1. **Internally**, mounted on the top of the uConsole, and connected inside the uConsole through the exposed 4-pin connector, **or**
2. **Externally**, using any other computer, as a standalone portable interface connected via **USB-C**.

This flexibility allows the board to serve as both a fixed and field-portable digital interface for modern ham operators.

---

## 🛠️ Hardware Update 
### (2025-11-11)

While the **first prototype** is being manufactured by **PCBWay**, I’ve made a few **minor improvements** to the design — primarily noted by my enclosure CAD work and manufacturing feedback.

This revision will use a **4-layer PCB** instead of the original 6-layer design. I’ll be experimenting with this to evaluate whether it provides sufficient signal integrity and isolation.

####  Design Changes
-  **SMA connector** changed to a **panel-mount** version for improved mechanical strength and enclosure fit.  
-  **USB connector** changed from **vertical** to **horizontal** orientation for better cable clearance.  
-  **BOM updated** — now includes full **Manufacturer Part Numbers (MPNs)** to streamline fabrication and assembly.  
-  **Component updates:** minor changes in package size and component values based on PCB manufacturer feedback (no functional impact).

---

> These refinements aim to simplify production, improve mechanical integration, and test a more cost-effective 4-layer configuration without compromising RF or audio performance.


![uConsole HAM Radio HAT PCB - rev01](/Pictures/Screenshot 2025-11-11 223535.png)

### (2025-11-01)
I used an original Digirig I had on hand to connect one of the SA818S modules I received from NiceRF in order to test the proof of concept (POC) before proceeding with the PCB order. I used the program from [SRFRS](https://github.com/jumbo5566/SRFRS). All OK.

### (2025-10-30)

The **PCB design is complete**, and I’m performing final checks before submitting the first production batch.

![uConsole HAM Radio HAT PCB](/Pictures/uConsole_HAM_HAT_PCB_render.png)


---

## 📡 Status

- ✅ Hardware design finalized  
- 🔄 Firmware and software integration in progress  
- 🚀 Initial board order planned for early November 2025

---

## ⚙️ Future Plans

- Add 70 cm band support  
- Optional GPS and APRS integration  
- Extended software control through uConsole UI  

---

## 📞 Contact

For collaboration, testing, or feedback, please open a GitHub issue or contact the maintainer directly.

---