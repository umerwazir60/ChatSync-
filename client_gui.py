import socket
import threading
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, scrolledtext
import os
import json
from game_utils import launch_tic_tac_toe
from file_utils import send_file
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChatClient:
    def __init__(self, master):
        self.master = master
        self.master.title("Chat Application")
        self.master.geometry("700x600")
        self.master.resizable(False, False)

        # Styling
        self.master.configure(bg='#f0f0f0')
        self.font = ('Arial', 12)
        self.bg_color = '#f0f0f0'
        self.button_color = '#4CAF50'
        self.button_active_color = '#45a049'
        self.text_bg = '#ffffff'
        self.text_fg = '#000000'

        # Main frame
        main_frame = tk.Frame(self.master, bg=self.bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Online users listbox
        self.users_listbox = tk.Listbox(main_frame, width=20, font=self.font, bg=self.text_bg, fg=self.text_fg)
        self.users_listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.users_listbox.bind('<<ListboxSelect>>', self.select_user)

        # Chat area
        self.chat_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=50, height=25, state='disabled',
                                                  font=self.font, bg=self.text_bg, fg=self.text_fg)
        self.chat_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat_area.tag_configure('sent', justify='right', foreground='blue')
        self.chat_area.tag_configure('received', justify='left', foreground='black')
        self.chat_area.tag_configure('system', justify='center', foreground='green')

        # Message entry frame
        entry_frame = tk.Frame(self.master, bg=self.bg_color)
        entry_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.target_var = tk.StringVar(value="Public")
        self.target_menu = tk.OptionMenu(entry_frame, self.target_var, "Public")
        self.target_menu.config(font=self.font, bg=self.button_color, fg='white', activebackground=self.button_active_color)
        self.target_menu.pack(side=tk.LEFT, padx=(0, 5))
        
        self.entry = tk.Entry(entry_frame, width=40, font=self.font)
        self.entry.pack(side=tk.LEFT, padx=(0, 5))
        self.entry.bind("<Return>", lambda event: self.send_message())

        self.send_button = tk.Button(entry_frame, text="Send", command=self.send_message, font=self.font,
                                    bg=self.button_color, fg='white', activebackground=self.button_active_color)
        self.send_button.pack(side=tk.LEFT)

        # Menu bar
        self.menu_bar = tk.Menu(self.master, font=self.font)
        self.master.config(menu=self.menu_bar)

        # Groups menu
        self.group_menu = tk.Menu(self.menu_bar, tearoff=0, font=self.font)
        self.group_menu.add_command(label="Create Private Group", command=self.create_private_group)
        self.group_menu.add_command(label="Join Private Group", command=self.join_private_group)
        self.group_menu.add_command(label="Leave Group", command=self.leave_group)
        self.group_menu.add_command(label="Kick User (Admin)", command=self.kick_user)
        self.menu_bar.add_cascade(label="Groups", menu=self.group_menu)

        # Files menu
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0, font=self.font)
        self.file_menu.add_command(label="Send File", command=self.send_file_dialog)
        self.menu_bar.add_cascade(label="Files", menu=self.file_menu)

        # Games menu
        self.game_menu = tk.Menu(self.menu_bar, tearoff=0, font=self.font)
        self.game_menu.add_command(label="Start Tic Tac Toe", command=self.start_tic_tac_toe)
        self.menu_bar.add_cascade(label="Games", menu=self.game_menu)

        self.master.protocol("WM_DELETE_WINDOW", self.close_connection)
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = None
        self.groups = []
        self.online_users = []
        self.connect_to_server()

    def connect_to_server(self):
        self.username = simpledialog.askstring("Username", "Enter your name:", parent=self.master)
        if not self.username:
            self.master.quit()
            return
        try:
            self.client_socket.connect(("127.0.0.1", 55555))
            self.client_socket.send(self.username.encode('utf-8'))
            threading.Thread(target=self.receive_messages, daemon=True).start()
            self.update_users_list()
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to server: {e}", parent=self.master)
            self.master.quit()

    def update_users_list(self):
        self.users_listbox.delete(0, tk.END)
        self.users_listbox.insert(tk.END, "Public")
        for group in self.groups:
            self.users_listbox.insert(tk.END, f"Group: {group}")
        for user in self.online_users:
            if user != self.username:
                self.users_listbox.insert(tk.END, user)
        self.target_menu['menu'].delete(0, tk.END)
        self.target_menu['menu'].add_command(label="Public", command=lambda: self.target_var.set("Public"))
        for group in self.groups:
            self.target_menu['menu'].add_command(label=f"Group: {group}", command=lambda g=group: self.target_var.set(f"Group: {g}"))
        for user in self.online_users:
            if user != self.username:
                self.target_menu['menu'].add_command(label=user, command=lambda u=user: self.target_var.set(u))

    def select_user(self, event):
        selection = self.users_listbox.get(tk.ACTIVE)
        if selection:
            self.target_var.set(selection)

    def receive_messages(self):
        while True:
            try:
                message = self.client_socket.recv(4096).decode('utf-8')
                if not message:
                    break
                logger.info(f"Received message: {message}")
                if message.startswith("/tictactoe_request"):
                    _, opponent, initiator = message.split(" ", 2)
                    response = messagebox.askyesno("Tic Tac Toe", f"{initiator} wants to play Tic Tac Toe. Accept?")
                    if response:
                        self.client_socket.send(f"/tictactoe_accept {initiator}".encode('utf-8'))
                    else:
                        self.client_socket.send(f"/tictactoe_decline {initiator}".encode('utf-8'))
                elif message.startswith("/tictactoe_start"):
                    _, opponent, initiator = message.split(" ", 2)
                    logger.info(f"Starting Tic Tac Toe: {initiator} vs {opponent}")
                    window = launch_tic_tac_toe(self.client_socket, opponent, initiator, self.username == initiator)
                    window.lift()
                    window.focus_force()
                elif message.startswith("/tictactoe_update"):
                    self.display_message(message, is_sent=False)
                elif message.startswith("FILE:"):
                    _, filename, filesize = message.split(":", 2)
                    self.client_socket.send("READY_TO_RECEIVE".encode('utf-8'))
                    self.receive_file(filename, filesize)
                elif message.startswith("Joined private group"):
                    group_name = message.split("'")[1]
                    self.groups.append(group_name)
                    self.update_users_list()
                    self.display_message(message, is_sent=False, tag='system')
                elif message.startswith("You left group") or message.startswith("Private group"):
                    self.display_message(message, is_sent=False, tag='system')
                    if message.startswith("You left group"):
                        group_name = message.split("'")[1]
                        if group_name in self.groups:
                            self.groups.remove(group_name)
                            self.update_users_list()
                elif message.endswith("has joined the chat.") or message.endswith("has left the chat."):
                    self.online_users = [u for u in self.online_users if not message.startswith(f"{u} has left")]
                    if "has joined" in message:
                        self.online_users.append(message.split(" has joined")[0])
                    self.update_users_list()
                    self.display_message(message, is_sent=False, tag='system')
                else:
                    self.display_message(message, is_sent=False)
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                self.display_message(f"Connection to server lost: {e}", is_sent=False, tag='system')
                break

    def receive_file(self, filename, filesize):
        try:
            remaining = int(filesize)
            data = b""
            while remaining:
                chunk = self.client_socket.recv(min(4096, remaining))
                if not chunk:
                    break
                data += chunk
                remaining -= len(chunk)
            from file_utils import save_file_from_bytes
            if save_file_from_bytes(data, filename):
                self.display_message(f"Received file: {filename}", is_sent=False, tag='system')
            else:
                self.display_message(f"Failed to save file: {filename}", is_sent=False, tag='system')
        except Exception as e:
            logger.error(f"Error receiving file: {e}")
            self.display_message(f"Error receiving file: {e}", is_sent=False, tag='system')

    def display_message(self, message, is_sent=False, tag='received'):
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, message + '\n', tag)
        self.chat_area.yview(tk.END)
        self.chat_area.config(state='disabled')

    def send_message(self):
        message = self.entry.get().strip()
        if message:
            target = self.target_var.get()
            if target == "Public":
                self.client_socket.send(message.encode('utf-8'))
                if not message.startswith(("/create", "/join", "/leave", "/kick", "/tictactoe")):
                    self.display_message(f"{self.username}: {message}", is_sent=True, tag='sent')
            elif target.startswith("Group: "):
                group_name = target[7:]
                self.client_socket.send(f"/groupmsg {group_name} {message}".encode('utf-8'))
                self.display_message(f"[{group_name}] {self.username}: {message}", is_sent=True, tag='sent')
            else:
                self.client_socket.send(f"@{target} {message}".encode('utf-8'))
                self.display_message(f"[Private to {target}]: {message}", is_sent=True, tag='sent')
            self.entry.delete(0, tk.END)

    def create_private_group(self):
        group_name = simpledialog.askstring("Create Private Group", "Enter group name:", parent=self.master)
        if group_name:
            password = simpledialog.askstring("Group Password", "Set group password:", parent=self.master, show='*')
            if password:
                self.client_socket.send(f"/create {group_name} {password}".encode('utf-8'))

    def join_private_group(self):
        group_name = simpledialog.askstring("Join Private Group", "Enter group name:", parent=self.master)
        if group_name:
            password = simpledialog.askstring("Group Password", "Enter group password:", parent=self.master, show='*')
            if password:
                self.client_socket.send(f"/join {group_name} {password}".encode('utf-8'))

    def leave_group(self):
        group_name = simpledialog.askstring("Leave Group", "Enter group name:", parent=self.master)
        if group_name:
            self.client_socket.send(f"/leave {group_name}".encode('utf-8'))

    def kick_user(self):
        group_name = simpledialog.askstring("Kick User", "Enter group name:", parent=self.master)
        if group_name:
            username = simpledialog.askstring("Kick User", "Enter username to kick:", parent=self.master)
            if username:
                self.client_socket.send(f"/kick {group_name} {username}".encode('utf-8'))

    def start_tic_tac_toe(self):
        opponent = simpledialog.askstring("Tic Tac Toe", "Enter opponent's username:", parent=self.master)
        if opponent:
            self.client_socket.send(f"/tictactoe_request {opponent} {self.username}".encode('utf-8'))

    def send_file_dialog(self):
        target = self.target_var.get()
        if target == "Public":
            messagebox.showwarning("Invalid Target", "Please select a group or user to send the file to.", parent=self.master)
            return
        filepath = filedialog.askopenfilename(parent=self.master)
        if filepath:
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            target_type = "group" if target.startswith("Group: ") else "private"
            target_name = target[7:] if target_type == "group" else target
            self.client_socket.send(f"/file:{target_type}:{target_name}:{filename}:{filesize}".encode('utf-8'))
            if send_file(self.client_socket, filepath):
                self.display_message(f"Sent file: {filename} to {target}", is_sent=True, tag='sent')
            else:
                self.display_message(f"Failed to send file: {filename}", is_sent=False, tag='system')

    def close_connection(self):
        try:
            self.client_socket.send("/quit".encode('utf-8'))
            self.client_socket.close()
        except:
            pass
        self.master.quit()

if __name__ == "__main__":
    root = tk.Tk()
    client = ChatClient(root)
    root.mainloop()