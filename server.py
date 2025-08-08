import socket
import threading
import os
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Server Configuration
HOST = '127.0.0.1'
PORT = 55555

# Data structures with lock for thread safety
lock = threading.Lock()
clients = {}  # conn -> addr
usernames = {}  # conn -> username
groups = {}  # group_name -> {'admin': conn, 'password': str, 'members': [conn]}
games = {}  # (player1, player2) -> game_state

def broadcast(message, sender_conn=None, group=None):
    with lock:
        if group and group in groups:
            for member in groups[group]['members']:
                if member != sender_conn:
                    try:
                        member.send(message.encode('utf-8'))
                    except Exception as e:
                        logger.error(f"Error broadcasting to member: {e}")
                        remove_client(member)
        else:
            for client in clients:
                if client != sender_conn:
                    try:
                        client.send(message.encode('utf-8'))
                    except Exception as e:
                        logger.error(f"Error broadcasting to client: {e}")
                        remove_client(client)

def send_private_message(message, sender_conn, recipient_username):
    with lock:
        for conn, username in usernames.items():
            if username == recipient_username:
                try:
                    conn.send(f"[Private] {usernames[sender_conn]}: {message}".encode('utf-8'))
                    sender_conn.send(f"[Private to {recipient_username}]: {message}".encode('utf-8'))
                    return
                except Exception as e:
                    logger.error(f"Error sending private message: {e}")
                    remove_client(conn)
                    return
        sender_conn.send(f"User {recipient_username} not found.".encode('utf-8'))

def receive_file(conn, target_type, target, filename, filesize):
    try:
        os.makedirs("server_files", exist_ok=True)
        filepath = os.path.join("server_files", filename)
        with open(filepath, "wb") as f:
            remaining = int(filesize)
            while remaining:
                data = conn.recv(min(4096, remaining))
                if not data:
                    break
                f.write(data)
                remaining -= len(data)
        with open(filepath, "rb") as f:
            file_data = f.read()
        with lock:
            if target_type == "group" and target in groups:
                for member in groups[target]['members']:
                    if member != conn:
                        try:
                            member.send(f"FILE:{filename}:{len(file_data)}".encode('utf-8'))
                            member.recv(1024)  # Wait for READY_TO_RECEIVE
                            member.sendall(file_data)
                        except Exception as e:
                            logger.error(f"Error sending file to group member: {e}")
                            remove_client(member)
            elif target_type == "private":
                for c, uname in usernames.items():
                    if uname == target and c != conn:
                        try:
                            c.send(f"FILE:{filename}:{len(file_data)}".encode('utf-8'))
                            c.recv(1024)
                            c.sendall(file_data)
                        except Exception as e:
                            logger.error(f"Error sending file to private user: {e}")
                            remove_client(c)
            else:
                conn.send(f"Invalid target: {target}".encode('utf-8'))
    except Exception as e:
        logger.error(f"Error receiving file: {e}")
        conn.send(f"Error receiving file: {e}".encode('utf-8'))

def handle_tic_tac_toe(conn, opponent_username, idx, player):
    with lock:
        for c, uname in usernames.items():
            if uname == opponent_username:
                try:
                    c.send(f"/tictactoe_update {json.dumps({'index': int(idx), 'player': player})}".encode('utf-8'))
                    return
                except Exception as e:
                    logger.error(f"Error handling tic-tac-toe update: {e}")
                    remove_client(c)
                    return
        conn.send(f"Invalid opponent: {opponent_username}".encode('utf-8'))

def remove_client(conn):
    with lock:
        if conn in clients:
            username = usernames.get(conn, "Unknown")
            del usernames[conn]
            del clients[conn]
            for group_name, group_info in list(groups.items()):
                if conn in group_info['members']:
                    group_info['members'].remove(conn)
                    if group_info['admin'] == conn:
                        if group_info['members']:
                            group_info['admin'] = group_info['members'][0]
                            group_info['members'][0].send(f"You are now the admin of {group_name}".encode('utf-8'))
                        else:
                            del groups[group_name]
                    broadcast(f"{username} has left the group {group_name}.", group=group_name)
            for (p1, p2) in list(games.keys()):
                if p1 == conn or p2 == conn:
                    opponent = p2 if p1 == conn else p1
                    try:
                        opponent.send("/tictactoe_end".encode('utf-8'))
                    except:
                        pass
                    del games[(p1, p2)]
            conn.close()
            broadcast(f"{username} has left the chat.")

def handle_client(conn, addr):
    try:
        username = conn.recv(1024).decode('utf-8')
        if not username:
            return
        with lock:
            usernames[conn] = username
            clients[conn] = addr
        logger.info(f"{username} connected from {addr}.")
        broadcast(f"{username} has joined the chat.", conn)

        while True:
            msg = conn.recv(4096).decode('utf-8')
            if not msg:
                break
            logger.info(f"Received from {username}: {msg}")
            try:
                if msg.startswith("/create"):
                    _, group_name, password = msg.split(" ", 2)
                    with lock:
                        if group_name not in groups:
                            groups[group_name] = {'admin': conn, 'password': password, 'members': [conn]}
                            conn.send(f"Private group '{group_name}' created.".encode('utf-8'))
                        else:
                            conn.send(f"Group '{group_name}' already exists.".encode('utf-8'))
                elif msg.startswith("/join"):
                    _, group_name, password = msg.split(" ", 2)
                    with lock:
                        if group_name in groups and groups[group_name]['password'] == password:
                            groups[group_name]['members'].append(conn)
                            conn.send(f"Joined private group '{group_name}'.".encode('utf-8'))
                            broadcast(f"{username} has joined the group {group_name}.", conn, group_name)
                        else:
                            conn.send(f"Invalid group name or password.".encode('utf-8'))
                elif msg.startswith("/leave"):
                    _, group_name = msg.split(" ", 1)
                    with lock:
                        if group_name in groups and conn in groups[group_name]['members']:
                            groups[group_name]['members'].remove(conn)
                            if groups[group_name]['admin'] == conn:
                                if groups[group_name]['members']:
                                    groups[group_name]['admin'] = groups[group_name]['members'][0]
                                    groups[group_name]['members'][0].send(f"You are now the admin of {group_name}".encode('utf-8'))
                                else:
                                    del groups[group_name]
                            conn.send(f"You left group '{group_name}'.".encode('utf-8'))
                            broadcast(f"{username} has left the group {group_name}.", group=group_name)
                        else:
                            conn.send(f"You are not in group '{group_name}'.".encode('utf-8'))
                elif msg.startswith("/kick"):
                    _, group_name, target_username = msg.split(" ", 2)
                    with lock:
                        if group_name in groups and groups[group_name]['admin'] == conn:
                            for c, uname in usernames.items():
                                if uname == target_username and c in groups[group_name]['members']:
                                    groups[group_name]['members'].remove(c)
                                    c.send(f"You were kicked from group '{group_name}'.".encode('utf-8'))
                                    broadcast(f"{target_username} was kicked from group {group_name}.", group=group_name)
                                    break
                            else:
                                conn.send(f"User {target_username} not found in group {group_name}.".encode('utf-8'))
                        else:
                            conn.send(f"You are not the admin of '{group_name}'.".encode('utf-8'))
                elif msg.startswith("/file:"):
                    _, target_type, target, filename, filesize = msg.split(":", 4)
                    conn.send("READY".encode('utf-8'))
                    receive_file(conn, target_type, target, filename, filesize)
                elif msg.startswith("/tictactoe_request"):
                    _, opponent, initiator = msg.split(" ", 2)
                    with lock:
                        for c, uname in usernames.items():
                            if uname == opponent:
                                c.send(f"/tictactoe_request {initiator} {opponent}".encode('utf-8'))
                                break
                        else:
                            conn.send(f"User {opponent} not found.".encode('utf-8'))
                elif msg.startswith("/tictactoe_accept"):
                    _, opponent = msg.split(" ", 1)
                    initiator = None
                    with lock:
                        for c, uname in usernames.items():
                            if uname == opponent:
                                initiator = c
                                break
                        if initiator and initiator in clients and conn in clients:  # Ensure both players are connected
                            games[(initiator, conn)] = {'board': ['' for _ in range(9)]}
                            initiator_username = usernames[initiator]
                            conn_username = usernames[conn]
                            try:
                                initiator.send(f"/tictactoe_start {conn_username} {initiator_username}".encode('utf-8'))
                                conn.send(f"/tictactoe_start {initiator_username} {conn_username}".encode('utf-8'))
                                logger.info(f"Started Tic Tac Toe: {initiator_username} vs {conn_username}")
                            except Exception as e:
                                logger.error(f"Error starting Tic Tac Toe: {e}")
                                if initiator in clients:
                                    initiator.send(f"Failed to start game with {conn_username}.".encode('utf-8'))
                                if conn in clients:
                                    conn.send(f"Failed to start game with {initiator_username}.".encode('utf-8'))
                        else:
                            conn.send(f"User {opponent} not available.".encode('utf-8'))
                elif msg.startswith("/tictactoe_decline"):
                    _, opponent = msg.split(" ", 1)
                    with lock:
                        for c, uname in usernames.items():
                            if uname == opponent:
                                c.send(f"{usernames[conn]} declined your Tic Tac Toe request.".encode('utf-8'))
                                break
                elif msg.startswith("/tictactoe"):
                    _, opponent, idx, player = msg.split(" ", 3)
                    handle_tic_tac_toe(conn, opponent, idx, player)
                elif msg.startswith("/groupmsg"):
                    _, group_name, group_msg = msg.split(" ", 2)
                    with lock:
                        if group_name in groups and conn in groups[group_name]['members']:
                            broadcast(f"[{group_name}] {usernames[conn]}: {group_msg}", conn, group_name)
                        else:
                            conn.send(f"You are not in group '{group_name}'.".encode('utf-8'))
                elif msg.startswith("@"):
                    recipient, message = msg[1:].split(" ", 1)
                    send_private_message(message, conn, recipient)
                elif msg.startswith("/quit"):
                    break
                else:
                    broadcast(f"{usernames[conn]}: {msg}", conn)
            except Exception as e:
                logger.error(f"Error processing message from {username}: {e}")
    except Exception as e:
        logger.error(f"Error handling client {username}: {e}")
    finally:
        remove_client(conn)

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    logger.info(f"Server running on {HOST}:{PORT}...")
    while True:
        try:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.start()
        except Exception as e:
            logger.error(f"Error accepting connection: {e}")

if __name__ == "__main__":
    start_server()