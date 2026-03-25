import customtkinter as ctk
from tkinter import filedialog as fd
import cv2
import mediapipe as mp
import socket
import threading
import time
import math
import collections
from PIL import Image
import os
import random

# --- Core Setup & Styling ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

TCP_PORT = 8888
UDP_PORT = 8889
NEON_CYAN = (255, 255, 0)
NEON_PURPLE = (255, 0, 255)

class QuickShareNative(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Quick Share | Native P2P Transfer")
        self.geometry("900x750")
        self.resizable(False, False)
        
        # Ensure webcam cleanly shuts off when app is closed
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # App State
        self.role = None
        self.connection = None
        self.is_connected = False
        self.camera_active = False
        self.cap = None

        # Data Transfer State
        self.filepath = None
        self.filename = ""
        self.filesize = 0
        self.otp = None
        
        # Gesture State
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
        self.mp_draw = mp.solutions.drawing_utils
        self.is_grabbing = False
        self.file_pos = [0, 0]
        self.velocity_buffer = collections.deque(maxlen=5)
        self.file_sent = False
        self.incoming_alert = False
        self.file_caught = False

        self.show_home()

    def on_closing(self):
        """Safely release the camera and close all network threads before exiting."""
        self.camera_active = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        try:
            if self.connection:
                self.connection.close()
        except:
            pass
        self.destroy()

    # ==========================================
    # UI: SCREENS & NAVIGATION
    # ==========================================
    def clear_ui(self):
        for widget in self.winfo_children():
            widget.destroy()

    def show_home(self):
        self.clear_ui()
        self.camera_active = False

        ctk.CTkLabel(self, text="QUICK SHARE", font=("Helvetica", 45, "bold"), text_color="#00f2fe").pack(pady=(100, 10))
        ctk.CTkLabel(self, text="Direct Device-to-Device Gesture Transfer", font=("Helvetica", 16)).pack(pady=(0, 50))

        ctk.CTkButton(self, text="🟢 SENDER (Select File & Throw)", width=300, height=60, 
                      font=("Helvetica", 16, "bold"), command=self.init_sender).pack(pady=15)
        ctk.CTkButton(self, text="🔵 RECEIVER (Enter OTP & Catch)", width=300, height=60, 
                      font=("Helvetica", 16, "bold"), command=self.show_receiver_login).pack(pady=15)

    def init_sender(self):
        self.filepath = fd.askopenfilename(title="Select File to Transfer")
        if not self.filepath: return # User clicked cancel
            
        self.filename = os.path.basename(self.filepath)
        self.filesize = os.path.getsize(self.filepath)
        self.role = "SENDER"
        self.otp = str(random.randint(1000, 9999))
        
        # Start background network listeners
        threading.Thread(target=self.udp_otp_broadcaster, daemon=True).start()
        threading.Thread(target=self.tcp_file_server, daemon=True).start()
        
        self.show_camera_hud()

    def show_receiver_login(self):
        self.clear_ui()
        ctk.CTkLabel(self, text="Enter 4-Digit OTP", font=("Helvetica", 28, "bold")).pack(pady=(150, 20))
        self.otp_entry = ctk.CTkEntry(self, placeholder_text="0000", width=250, height=60, font=("Helvetica", 32, "bold"), justify="center")
        self.otp_entry.pack(pady=15)
        ctk.CTkButton(self, text="Find Sender", width=250, height=50, font=("Helvetica", 16, "bold"), command=self.init_receiver).pack(pady=20)
        ctk.CTkButton(self, text="Back", fg_color="transparent", hover_color="#333333", command=self.show_home).pack()

    def init_receiver(self):
        entered_otp = self.otp_entry.get().strip()
        if len(entered_otp) == 4:
            self.role = "RECEIVER"
            self.show_camera_hud()
            self.update_hud(f"SEARCHING WI-FI FOR OTP {entered_otp}...", "#ffcc00")
            threading.Thread(target=self.udp_discover_sender, args=(entered_otp,), daemon=True).start()

    def show_camera_hud(self):
        self.clear_ui()
        
        # Heads Up Display (HUD)
        self.hud_frame = ctk.CTkFrame(self, height=90, corner_radius=10, fg_color="#1a1a1a")
        self.hud_frame.pack(fill="x", side="top", padx=20, pady=10)
        
        initial_text = f"OTP: {self.otp} | Waiting for Receiver..." if self.role == "SENDER" else "INITIALIZING CAMERA..."
        self.status_label = ctk.CTkLabel(self.hud_frame, text=initial_text, font=("Helvetica", 18, "bold"), text_color="#00f2fe")
        self.status_label.pack(pady=10)

        self.progress_bar = ctk.CTkProgressBar(self.hud_frame, width=500, height=12)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=5)
        if self.role == "SENDER": self.progress_bar.pack_forget() # Hide until transfer

        # Video Feed
        self.video_label = ctk.CTkLabel(self, text="")
        self.video_label.pack(expand=True, fill="both", padx=20, pady=10)

        # Open Camera
        self.cap = cv2.VideoCapture(0)
        self.camera_active = True
        self.update_camera_frame()

    # ==========================================
    # TRUE PEER-TO-PEER NETWORKING
    # ==========================================
    def udp_otp_broadcaster(self):
        """SENDER: Listens for the Receiver shouting the OTP on the local network."""
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(('0.0.0.0', UDP_PORT))
        while not self.is_connected and self.camera_active:
            data, addr = udp.recvfrom(1024)
            if data.decode('utf-8') == self.otp:
                udp.sendto(b"OTP_MATCH_CONFIRMED", addr) # Reply to Receiver
                break
        udp.close()

    def tcp_file_server(self):
        """SENDER: Opens a direct pipeline for the file bytes."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('0.0.0.0', TCP_PORT))
        server.listen(1)
        self.connection, addr = server.accept()
        self.is_connected = True
        self.update_hud(f"CONNECTED TO RECEIVER! Pinch to grab {self.filename}", "#00ff00")

    def udp_discover_sender(self, target_otp):
        """RECEIVER: Shouts the OTP to the entire Wi-Fi network to find the Sender."""
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.settimeout(10.0)
        
        try:
            udp.sendto(target_otp.encode('utf-8'), ('255.255.255.255', UDP_PORT))
            data, addr = udp.recvfrom(1024)
            if data == b"OTP_MATCH_CONFIRMED":
                sender_ip = addr[0]
                self.update_hud(f"SENDER FOUND! Connecting to {sender_ip}...", "#00f2fe")
                
                # Establish direct TCP pipeline
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect((sender_ip, TCP_PORT))
                self.connection = client
                self.is_connected = True
                self.update_hud("CONNECTED! Wait for the sender to throw.", "#00ff00")
                self.receive_file_stream()
        except socket.timeout:
            self.update_hud("OTP NOT FOUND. Ensure devices are on same Wi-Fi.", "#ff4444")
        finally:
            udp.close()

    def transfer_file_stream(self):
        """SENDER: Pushes raw bytes directly to Receiver."""
        if self.connection and not self.file_sent:
            try:
                self.progress_bar.pack(pady=5)
                # 1. Send Metadata (Name and Size)
                header = f"THROW_META|{self.filename}|{self.filesize}".encode('utf-8')
                self.connection.sendall(header + b":::END_META:::")
                time.sleep(0.5)
                
                # 2. Stream File Bytes
                bytes_sent = 0
                with open(self.filepath, "rb") as f:
                    while chunk := f.read(8192): # 8KB chunks for stable local transfer
                        self.connection.sendall(chunk)
                        bytes_sent += len(chunk)
                        self.progress_bar.set(bytes_sent / self.filesize)
                        self.update_idletasks() # Keep UI responsive
                
                self.file_sent = True
                self.update_hud("FILE SENT SUCCESSFULLY! 🚀", "#00ff00")
            except Exception as e:
                self.update_hud(f"TRANSFER FAILED: Network Disconnected.", "#ff4444")

    def receive_file_stream(self):
        """RECEIVER: Pulls raw bytes directly from Sender and saves to Disk."""
        try:
            # 1. Wait for Throw metadata
            meta_data = b""
            while b":::END_META:::" not in meta_data:
                meta_data += self.connection.recv(1024)
            
            meta_string = meta_data.split(b":::END_META:::")[0].decode('utf-8')
            _, self.filename, filesize_str = meta_string.split("|")
            self.filesize = int(filesize_str)
            
            self.incoming_alert = True
            self.update_hud(f"INCOMING: {self.filename}! Open hand to CATCH!", "#00f2fe")
            
            # 2. Wait for physical catch gesture before saving (UX magic)
            while not self.file_caught:
                time.sleep(0.1)

            # 3. Save File Stream to system Downloads folder
            save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            save_path = os.path.join(save_dir, f"QuickShare_{self.filename}")
            
            self.progress_bar.pack(pady=5)
            bytes_received = 0
            with open(save_path, "wb") as f:
                while bytes_received < self.filesize:
                    chunk = self.connection.recv(8192)
                    if not chunk: break
                    f.write(chunk)
                    bytes_received += len(chunk)
                    self.progress_bar.set(bytes_received / self.filesize)
                    self.update_idletasks()
            
            self.update_hud(f"FILE SAVED TO DOWNLOADS FOLDER! 🎉", "#00ff00")
        except Exception as e:
            self.update_hud("TRANSFER INTERRUPTED.", "#ff4444")

    def update_hud(self, text, color):
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.configure(text=text, text_color=color)

    # ==========================================
    # COMPUTER VISION & PHYSICS ENGINE
    # ==========================================
    def update_camera_frame(self):
        if not self.camera_active or not self.cap.isOpened(): return

        success, frame = self.cap.read()
        if success:
            frame = cv2.flip(frame, 1) 
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)

            if results.multi_hand_landmarks and self.is_connected:
                for hand_lms in results.multi_hand_landmarks:
                    thumb = hand_lms.landmark[4]
                    index = hand_lms.landmark[8]
                    palm = hand_lms.landmark[9]
                    
                    dist = math.sqrt((thumb.x - index.x)**2 + (thumb.y - index.y)**2)

                    # --- SENDER PHYSICS ---
                    if self.role == "SENDER" and not self.file_sent:
                        if dist < 0.05: # Pinch gesture threshold
                            self.is_grabbing = True
                            self.update_hud(f"GRABBING {self.filename}. Flick right to THROW!", "#ff00ff")
                            self.file_pos = [int(index.x * w), int(index.y * h)]
                        else:
                            self.is_grabbing = False
                            self.update_hud(f"READY. Pinch fingers to grab.", "#00ff00")

                        # Throw Velocity Detection
                        self.velocity_buffer.append(palm.x)
                        if len(self.velocity_buffer) == 5 and self.is_grabbing:
                            if (self.velocity_buffer[-1] - self.velocity_buffer[0]) > 0.15: 
                                threading.Thread(target=self.transfer_file_stream, daemon=True).start()
                                self.is_grabbing = False

                    # --- RECEIVER PHYSICS ---
                    elif self.role == "RECEIVER" and self.incoming_alert and not self.file_caught:
                        if dist > 0.15: # Open hand gesture threshold
                            self.file_caught = True
                            self.update_hud(f"CATCHING FILE... DOWNLOADING!", "#00ff00")

                    # Draw skeleton map
                    self.mp_draw.draw_landmarks(frame, hand_lms, self.mp_hands.HAND_CONNECTIONS)

            # --- AR VISUALS ---
            if self.role == "SENDER" and self.is_grabbing:
                cv2.circle(frame, (self.file_pos[0], self.file_pos[1]), 40, NEON_PURPLE, -1)
                # Display file extension (e.g., PDF, JPG) inside the orb
                ext = self.filename.split('.')[-1][:3].upper() if '.' in self.filename else "DOC"
                cv2.putText(frame, ext, (self.file_pos[0]-18, self.file_pos[1]+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            
            if self.role == "RECEIVER" and self.incoming_alert and not self.file_caught:
                x_anim = int(time.time() * 1000 % w)
                cv2.circle(frame, (x_anim, h//2), 40, NEON_CYAN, -1)

            # Render OpenCV Frame to CustomTkinter GUI
            img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(w, h))
            self.video_label.configure(image=img_ctk)

        if self.camera_active:
            self.after(15, self.update_camera_frame)

if __name__ == "__main__":
    app = QuickShareNative()
    app.mainloop()
