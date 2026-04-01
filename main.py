# Pack Mehdi Pro V8 (PRO MAX - TESLA EDITION): CustomTkinter GUI + IA + Voix + Excel
# Developed by: MEHDI (2026)

import cv2
import mediapipe as mp
import math, time, threading, csv, os
from datetime import datetime
from collections import deque
import pyttsx3 
from twilio.rest import Client
from config import ACCOUNT_SID, AUTH_TOKEN, NUMERO_TWILIO, NUMERO_PERSO

# ---- 🎨 IMPORTATION DES NOUVEAUX MOTEURS GUI ----
import customtkinter as ctk
from PIL import Image

# ---- 🚀 INITIALISATION YOLOv8 ----
try:
    from ultralytics import YOLO
    modele_yolo = YOLO("best.pt") 
    yolo_actif = True
    print("✅ YOLOv8 chargé avec succès !")
except Exception as e:
    yolo_actif = False
    print("❌ Erreur YOLOv8:", e)

# ---- 🗣️ VOIX, DOSSIER & EXCEL ----
def task_parler(message):
    try:
        moteur = pyttsx3.init()
        moteur.setProperty('rate', 150) 
        moteur.say(message)
        moteur.runAndWait()
    except: pass

DOSSIER_PREUVES = "Preuves_Infractions"
if not os.path.exists(DOSSIER_PREUVES): os.makedirs(DOSSIER_PREUVES)

FICHIER_LOG = "historique_conduite.csv"
if not os.path.exists(FICHIER_LOG):
    with open(FICHIER_LOG, mode='w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(["Date", "Heure", "Type", "Détails", "Preuve", "Score"]) 

def log_evenement(type_infraction, details, nom_image, score):
    now = datetime.now()
    try:
        with open(FICHIER_LOG, mode='a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), type_infraction, details, nom_image, f"{score}%"])
    except: pass

try: client_twilio = Client(ACCOUNT_SID, AUTH_TOKEN)
except: pass
def envoyer_sms(msg): threading.Thread(target=lambda m: client_twilio.messages.create(body=m, from_=NUMERO_TWILIO, to=NUMERO_PERSO), args=(msg,)).start()

# ---- 🧠 MOTEUR MEDIAPIPE (MATHS) ----
OEIL_GAUCHE, OEIL_DROIT = [362, 385, 387, 263, 373, 380], [33,  160, 158, 133, 153, 144]
BOUCHE, COIN_DROIT, COIN_GAUCHE, NEZ = [13, 14, 78, 308], 33, 263, 1
SEUIL_MAR, SEUIL_ANGLE = 0.60, 25
SEUIL_TEMPS_YEUX, SEUIL_TEMPS_BOUCHE, SEUIL_TEMPS_TETE, SEUIL_TEMPS_REGARD = 2.0, 1.0, 2.0, 2.0
DELAI_SMS = 60

def distance(p1, p2): return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)
def calculer_ear(points, indices):
    p1, p2, p3, p4, p5, p6 = [points[idx] for idx in indices]
    return (distance(p2, p6) + distance(p3, p5)) / (2.0 * distance(p1, p4))
def calculer_mar(points, indices): return distance(points[indices[0]], points[indices[1]]) / distance(points[indices[2]], points[indices[3]])
def calculer_angle_tete(points): return math.degrees(math.atan2((points[COIN_GAUCHE].y - points[COIN_DROIT].y), (points[COIN_GAUCHE].x - points[COIN_DROIT].x)))
def calculer_yaw_tete(points):
    w = points[263].x - points[33].x
    return (points[NEZ].x - points[33].x) / w if w > 0 else 0.5
def calculer_gaze(points):
    xg_d, xd_d, xi_d = points[33].x, points[133].x, points[473].x
    rd = (xi_d - xg_d) / (xd_d - xg_d) if (xd_d - xg_d) > 0 else 0.5
    xg_g, xd_g, xi_g = points[362].x, points[263].x, points[468].x
    rg = (xi_g - xg_g) / (xd_g - xg_g) if (xd_g - xg_g) > 0 else 0.5
    return (rd + rg) / 2.0

# ==========================================
# 🎨 INTERFACE GRAPHIQUE (CustomTkinter)
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DriveSafeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DriveSafe PRO MAX - Tesla Edition")
        self.geometry("1100x650")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # ---- Variables Globales ----
        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened(): self.camera = cv2.VideoCapture(1)
        self.detecteur = mp.solutions.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)
        
        self.score_conduite = 100
        self.temps_debut = time.time()
        self.prev_frame_time = 0
        
        self.en_calibration = True
        self.debut_calib = time.time()
        self.valeurs_ear, self.valeurs_gaze, self.valeurs_angle, self.valeurs_yaw = [], [], [], []
        self.SEUIL_EAR, self.CENTRE_REGARD, self.ANGLE_TETE, self.CENTRE_YAW = 0.23, 0.5, 0.0, 0.5
        
        self.historique_blinks = []
        self.etat_clig = False
        self.historique_gaze, self.historique_yaw = deque(maxlen=7), deque(maxlen=7)
        self.temps_yeux = self.temps_bouche = self.temps_tete = self.temps_regard = None
        self.alarme_sound_playing = False
        self.dernier_sms = 0

        # ---- Mise en page (Layout) ----
        self.grid_columnconfigure(0, weight=1) # Video
        self.grid_columnconfigure(1, weight=0) # Panneau

        # 1. Cadre Vidéo (Gauche)
        self.video_frame = ctk.CTkFrame(self, corner_radius=15, fg_color="#121212")
        self.video_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.video_label = ctk.CTkLabel(self.video_frame, text="")
        self.video_label.pack(expand=True, fill="both", padx=10, pady=10)

        # 2. Panneau de Contrôle (Droite)
        self.panel = ctk.CTkFrame(self, width=350, corner_radius=15)
        self.panel.grid(row=0, column=1, padx=(0,20), pady=20, sticky="nsew")
        
        # Titre
        self.lbl_titre = ctk.CTkLabel(self.panel, text="DRIVE SAFE", font=ctk.CTkFont(size=30, weight="bold"), text_color="#00A5FF")
        self.lbl_titre.pack(pady=(20, 5))
        self.lbl_sub = ctk.CTkLabel(self.panel, text="Système ADAS Actif", font=ctk.CTkFont(size=14))
        self.lbl_sub.pack(pady=(0, 20))

        # Score
        self.lbl_score = ctk.CTkLabel(self.panel, text="SCORE: 100%", font=ctk.CTkFont(size=28, weight="bold"), text_color="#00FF00")
        self.lbl_score.pack(pady=10)

        # Chrono & FPS
        self.lbl_info = ctk.CTkLabel(self.panel, text="FPS: 0 | Temps: 00:00:00", font=ctk.CTkFont(size=14))
        self.lbl_info.pack(pady=10)

        # Boîtes de statut
        self.box_yeux = self.creer_status_box("STATUS YEUX", "Ouverts")
        self.box_regard = self.creer_status_box("DIRECTION REGARD", "Centre (Route)")
        self.box_yolo = self.creer_status_box("OBJETS DÉTECTÉS", "Aucun")
        
        self.lbl_alarme = ctk.CTkLabel(self.panel, text="VIGILANCE NORMALE", font=ctk.CTkFont(size=20, weight="bold"), fg_color="#2E2E2E", text_color="#00FF00", corner_radius=8, width=280, height=50)
        self.lbl_alarme.pack(pady=30)

        # Lancement de la boucle
        self.update_video()

    def creer_status_box(self, titre, valeur):
        cadre = ctk.CTkFrame(self.panel, fg_color="#2B2B2B", corner_radius=8, width=280, height=60)
        cadre.pack(pady=10)
        cadre.pack_propagate(False)
        ctk.CTkLabel(cadre, text=titre, font=ctk.CTkFont(size=12), text_color="#A0A0A0").pack(pady=(5,0))
        lbl_val = ctk.CTkLabel(cadre, text=valeur, font=ctk.CTkFont(size=18, weight="bold"), text_color="#00A5FF")
        lbl_val.pack()
        return lbl_val

    def update_video(self):
        ok, image = self.camera.read()
        if not ok: return

        image = cv2.flip(image, 1)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resultats_mp = self.detecteur.process(image_rgb)
        
        temps_actuel = time.time()
        fps = 1 / (temps_actuel - self.prev_frame_time) if self.prev_frame_time else 0
        self.prev_frame_time = temps_actuel
        
        duree = int(temps_actuel - self.temps_debut)
        self.lbl_info.configure(text=f"FPS: {int(fps)} | Temps: {duree//3600:02d}:{(duree%3600)//60:02d}:{duree%60:02d}")

        alarme_active = False
        objet_detecte, type_danger = None, None
        val_yeux, val_regard, c_yeux, c_regard = "Ouverts", "Centre (Route)", "#00A5FF", "#00A5FF"

        # YOLOv8
        if yolo_actif and not self.en_calibration:
            res = modele_yolo.predict(image, imgsz=320, conf=0.45, verbose=False)
            for r in res:
                for box in r.boxes:
                    cls_name = modele_yolo.names[int(box.cls[0])].lower()
                    if "phone" in cls_name or "cell" in cls_name: objet_detecte = "TELEPHONE"
                    elif "cig" in cls_name or "smoke" in cls_name: objet_detecte = "CIGARETTE"
                    
                    if objet_detecte:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(image_rgb, (x1, y1), (x2, y2), (255, 0, 0), 3) # Rouge en RGB
                        alarme_active = True
                        type_danger = objet_detecte

        # MediaPipe
        if resultats_mp.multi_face_landmarks:
            points = resultats_mp.multi_face_landmarks[0].landmark
            ear = (calculer_ear(points, OEIL_GAUCHE) + calculer_ear(points, OEIL_DROIT)) / 2.0
            mar = calculer_mar(points, BOUCHE)
            angle = calculer_angle_tete(points)
            gaze = calculer_gaze(points)
            yaw = calculer_yaw_tete(points)

            if self.en_calibration:
                if (temps_actuel - self.debut_calib) < 5.0:
                    self.valeurs_ear.append(ear); self.valeurs_gaze.append(gaze)
                    self.valeurs_angle.append(angle); self.valeurs_yaw.append(yaw)
                    cv2.putText(image_rgb, f"CALIBRATION: {int(5-(temps_actuel-self.debut_calib))}s", (50, 50), cv2.FONT_HERSHEY_DUPLEX, 1, (255,165,0), 2)
                else:
                    self.en_calibration = False
                    self.SEUIL_EAR = (sum(self.valeurs_ear)/len(self.valeurs_ear)) * 0.75
                    self.CENTRE_REGARD = sum(self.valeurs_gaze)/len(self.valeurs_gaze)
                    self.ANGLE_TETE = sum(self.valeurs_angle)/len(self.valeurs_angle)
                    self.CENTRE_YAW = sum(self.valeurs_yaw)/len(self.valeurs_yaw)
            else:
                self.historique_gaze.append(gaze); self.historique_yaw.append(yaw)
                offset = (sum(self.historique_yaw)/len(self.historique_yaw)) - self.CENTRE_YAW
                
                # Yeux
                if ear < self.SEUIL_EAR and abs(offset) < 0.15:
                    if not self.temps_yeux: self.temps_yeux = temps_actuel
                    dur = temps_actuel - self.temps_yeux
                    val_yeux = f"Closed {dur:.1f}s"
                    c_yeux = "#FFA500" if dur < SEUIL_TEMPS_YEUX else "#FF0000"
                    if dur >= SEUIL_TEMPS_YEUX: alarme_active = True; type_danger = type_danger or "SOMNOLENCE"
                else: self.temps_yeux = None

                # Regard
                gaze_cor = (sum(self.historique_gaze)/len(self.historique_gaze)) + (offset * 0.55)
                if gaze_cor < (self.CENTRE_REGARD - 0.14): dir_r = "Gauche (Distrait)"
                elif gaze_cor > (self.CENTRE_REGARD + 0.14): dir_r = "Droite (Distrait)"
                else: dir_r = "Centre (Route)"

                if dir_r != "Centre (Route)":
                    if not self.temps_regard: self.temps_regard = temps_actuel
                    dur = temps_actuel - self.temps_regard
                    val_regard = f"{dir_r} {dur:.1f}s"
                    c_regard = "#FFA500" if dur < SEUIL_TEMPS_REGARD else "#FF0000"
                    if dur >= SEUIL_TEMPS_REGARD: alarme_active = True; type_danger = type_danger or "DISTRACTION_REGARD"
                else: self.temps_regard = None; val_regard = dir_r
                
                # Baillement
                if mar > SEUIL_MAR:
                    if not self.temps_bouche: self.temps_bouche = temps_actuel
                    if temps_actuel - self.temps_bouche >= SEUIL_TEMPS_BOUCHE: alarme_active = True; type_danger = type_danger or "BAILLEMENT"
                else: self.temps_bouche = None

        # Gestion Alarme & GUI
        self.box_yeux.configure(text=val_yeux, text_color=c_yeux)
        self.box_regard.configure(text=val_regard, text_color=c_regard)
        self.box_yolo.configure(text=objet_detecte or "Aucun", text_color="#FF0000" if objet_detecte else "#00A5FF")

        if alarme_active and not self.en_calibration:
            self.lbl_alarme.configure(text=f"DANGER: {type_danger}", text_color="#FF0000", fg_color="#4A0000")
            if not self.alarme_sound_playing:
                self.alarme_sound_playing = True
                
                # Baisse Score
                if type_danger == "SOMNOLENCE": self.score_conduite -= 15
                elif type_danger == "TELEPHONE": self.score_conduite -= 10
                else: self.score_conduite -= 5
                self.score_conduite = max(0, self.score_conduite)
                self.lbl_score.configure(text=f"SCORE: {self.score_conduite}%", text_color="#00FF00" if self.score_conduite>75 else ("#FFA500" if self.score_conduite>50 else "#FF0000"))
                
                # Preuve & Log
                img_name = f"Preuve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(os.path.join(DOSSIER_PREUVES, img_name), cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
                threading.Thread(target=task_parler, args=(f"Attention, danger détecté !",)).start()
                log_evenement(type_danger, "Alerte déclenchée", img_name, self.score_conduite)
                
                if temps_actuel - self.dernier_sms > DELAI_SMS:
                    envoyer_sms(f"DANGER DriveSafe : {type_danger}! Score: {self.score_conduite}%")
                    self.dernier_sms = temps_actuel
        else:
            self.lbl_alarme.configure(text="VIGILANCE NORMALE", text_color="#00FF00", fg_color="#2E2E2E")
            self.alarme_sound_playing = False

        # Conversion Image pour Tkinter
        img_pil = Image.fromarray(image_rgb)
        imgtk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(750, 500))
        self.video_label.configure(image=imgtk)
        
        # Boucle
        self.after(15, self.update_video)

    def on_closing(self):
        self.camera.release()
        self.destroy()

if __name__ == "__main__":
    app = DriveSafeApp()
    app.mainloop()