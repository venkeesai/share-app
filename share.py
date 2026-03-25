import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, WebRtcMode, RTCConfiguration
import cv2
import mediapipe as mp
import math
import random
import av

# --- 1. PAGE CONFIGURATION & STYLING ---
st.set_page_config(page_title="Quick Share | Magical Transfer", page_icon="🪄", layout="centered")

# Custom CSS for Glassmorphism & Neon Theme
st.markdown("""
    <style>
    /* Dark Theme Background */
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }
    
    /* Glassmorphism Containers */
    div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 16px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
    }

    /* Neon Buttons */
    .stButton>button {
        background: linear-gradient(45deg, #00f2fe, #4facfe);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        transition: 0.3s;
        box-shadow: 0 0 10px rgba(0, 242, 254, 0.5);
    }
    .stButton>button:hover {
        background: linear-gradient(45deg, #4facfe, #00f2fe);
        box-shadow: 0 0 20px rgba(0, 242, 254, 0.8);
        transform: scale(1.02);
    }

    /* OTP Text Highlighting */
    .otp-text {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(#b224ef, #7579ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        letter-spacing: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE (Serverless DB) ---
if 'shared_files' not in st.session_state:
    st.session_state['shared_files'] = {}

# --- 3. COMPUTER VISION GESTURE ENGINE ---
class GestureProcessor(VideoTransformerBase):
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
        self.mp_draw = mp.solutions.drawing_utils
        self.status = "SCANNING HAND..."
        self.neon_cyan = (255, 255, 0) # OpenCV uses BGR
        self.neon_purple = (255, 0, 255)

    def calc_distance(self, p1, p2):
        return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1) # Mirror image for natural UX
        h, w, _ = img.shape
        
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_img)

        # Draw futuristic HUD
        cv2.rectangle(img, (0, 0), (w, 60), (20, 20, 20), -1)
        cv2.putText(img, f"AR HUD: {self.status}", (15, 40), cv2.FONT_HERSHEY_DUPLEX, 0.7, self.neon_cyan, 2)

        if results.multi_hand_landmarks:
            for hand_lms in results.multi_hand_landmarks:
                thumb = hand_lms.landmark[4]
                index = hand_lms.landmark[8]
                
                dist = self.calc_distance(thumb, index)
                cx, cy = int(index.x * w), int(index.y * h)

                # Physics & Visual Feedback
                if dist < 0.06:
                    self.status = "GRABBING FILE - THROW!"
                    # Draw a glowing digital orb
                    cv2.circle(img, (cx, cy), 45, self.neon_purple, -1)
                    cv2.circle(img, (cx, cy), 55, self.neon_purple, 2)
                    cv2.putText(img, "FILE", (cx-22, cy+5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                elif dist > 0.15:
                    self.status = "HAND OPEN - READY TO CATCH"
                    cv2.circle(img, (w//2, h//2), int(dist*300), self.neon_cyan, 2)
                else:
                    self.status = "TARGET ACQUIRED"

                # Draw skeleton map
                self.mp_draw.draw_landmarks(img, hand_lms, self.mp_hands.HAND_CONNECTIONS)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# WebRTC Config (Helps connect devices on different network topologies)
RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

# --- 4. MAIN APP UI ---
def main():
    st.markdown("<h1 style='text-align: center;'>🪄 Quick Share</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>Gesture-Based File Transfer</p>", unsafe_allow_html=True)
    
    # Role Selection
    role = st.radio("Select Interface Mode", ["📤 SENDER", "📥 RECEIVER"], horizontal=True)
    st.divider()

    # ================== SENDER FLOW ==================
    if role == "📤 SENDER":
        st.subheader("1. Upload Payload")
        uploaded_file = st.file_uploader("Select a file, image, or video", label_visibility="collapsed")
        
        if uploaded_file:
            # Create OTP and store file in session state
            if 'current_otp' not in st.session_state or st.session_state.get('last_file') != uploaded_file.name:
                otp = str(random.randint(1000, 9999))
                st.session_state['current_otp'] = otp
                st.session_state['last_file'] = uploaded_file.name
                
                st.session_state['shared_files'][otp] = {
                    "name": uploaded_file.name,
                    "data": uploaded_file.getvalue(),
                    "mime": uploaded_file.type
                }
            else:
                otp = st.session_state['current_otp']
            
            st.success(f"Payload secured: {uploaded_file.name}")
            
            st.markdown("### 2. Share this OTP")
            st.markdown(f"<div class='otp-text'>{otp}</div>", unsafe_allow_html=True)
            st.caption("Keep this tab open. Tell the receiver to enter this code, then pinch your fingers below to grab the file!")
            
            st.markdown("<br>", unsafe_allow_html=True)
            webrtc_streamer(
                key="sender-stream",
                mode=WebRtcMode.SENDRECV,
                rtc_configuration=RTC_CONFIG,
                video_transformer_factory=GestureProcessor,
                media_stream_constraints={"video": True, "audio": False},
                async_transform=True
            )

    # ================== RECEIVER FLOW ==================
    elif role == "📥 RECEIVER":
        st.subheader("1. Enter Pairing Code")
        entered_otp = st.text_input("Enter the 4-digit code", max_chars=4)
        
        if entered_otp:
            if entered_otp in st.session_state['shared_files']:
                file_info = st.session_state['shared_files'][entered_otp]
                st.success("Connection Established! 🟢")
                
                st.subheader("2. Catch & Download")
                st.caption("Open your hand to the camera to catch the incoming file.")
                
                # Camera Feed
                webrtc_streamer(
                    key="receiver-stream",
                    mode=WebRtcMode.SENDRECV,
                    rtc_configuration=RTC_CONFIG,
                    video_transformer_factory=GestureProcessor,
                    media_stream_constraints={"video": True, "audio": False},
                    async_transform=True
                )
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.download_button(
                    label=f"⬇️ Download {file_info['name']}",
                    data=file_info['data'],
                    file_name=f"QuickShare_{file_info['name']}",
                    mime=file_info['mime'],
                    use_container_width=True
                )
            elif len(entered_otp) == 4:
                st.error("Invalid OTP or Sender disconnected.")

if __name__ == "__main__":
    main()