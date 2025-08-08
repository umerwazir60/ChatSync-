import tkinter as tk
from tkinter import messagebox
import json
import threading
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def launch_tic_tac_toe(client_socket, opponent_username, initiator_username, is_initiator):
    window = tk.Toplevel()
    window.title(f"{initiator_username} vs {opponent_username}")
    window.geometry("300x350")
    window.resizable(False, False)
    window.configure(bg='#f0f0f0')
    window.lift()  # Bring window to front
    window.focus_force()  # Force focus on window

    current_player = 'X' if is_initiator else 'O'  # Initiator is X, opponent is O
    my_turn = is_initiator
    board = ['' for _ in range(9)]
    game_active = True

    def check_winner():
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in wins:
            if board[a] == board[b] == board[c] != '':
                return board[a]
        if '' not in board:
            return 'Draw'
        return None

    def click(idx):
        nonlocal my_turn, current_player, game_active
        if not my_turn or board[idx] or not game_active:
            return
        board[idx] = current_player
        buttons[idx].config(text=current_player)
        try:
            client_socket.send(f"/tictactoe {opponent_username} {idx} {current_player}".encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending tic-tac-toe move: {e}")
            messagebox.showerror("Error", f"Failed to send move: {e}")
            game_active = False
            window.destroy()
            return
        result = check_winner()
        if result:
            if result == 'Draw':
                messagebox.showinfo("Result", "It's a draw!")
            else:
                winner = initiator_username if result == 'X' else opponent_username
                messagebox.showinfo("Winner", f"{winner} wins!")
            game_active = False
            try:
                client_socket.send(f"/tictactoe_end {opponent_username}".encode('utf-8'))
            except:
                pass
            window.destroy()
        else:
            my_turn = False
            update_turn_label()

    def update_board(move_data):
        nonlocal my_turn, current_player, game_active
        try:
            idx = move_data['index']
            player = move_data['player']
            board[idx] = player
            buttons[idx].config(text=player)
            my_turn = True
            current_player = 'X' if player == 'O' else 'O'
            result = check_winner()
            if result:
                winner = initiator_username if result == 'X' else opponent_username
                if result == 'Draw':
                    messagebox.showinfo("Result", "It's a draw!")
                else:
                    messagebox.showinfo("Winner", f"{winner} wins!")
                game_active = False
                try:
                    client_socket.send(f"/tictactoe_end {opponent_username}".encode('utf-8'))
                except:
                    pass
                window.destroy()
            else:
                update_turn_label()
        except Exception as e:
            logger.error(f"Error updating board: {e}")
            messagebox.showerror("Error", f"Game error: {e}")
            game_active = False
            window.destroy()

    def update_turn_label():
        turn_text = f"Your turn ({current_player})" if my_turn else f"{opponent_username}'s turn"
        status_label.config(text=turn_text)

    def receive_game_updates():
        nonlocal game_active
        try:
            while game_active:
                msg = client_socket.recv(1024).decode('utf-8')
                if not msg:
                    break
                if msg.startswith("/tictactoe_update"):
                    _, data = msg.split(" ", 1)
                    update_board(json.loads(data))
                elif msg.startswith("/tictactoe_end"):
                    messagebox.showinfo("Game Ended", "Opponent ended the game.")
                    game_active = False
                    window.destroy()
                    break
        except Exception as e:
            logger.error(f"Error in game updates: {e}")
            if game_active:
                messagebox.showerror("Error", "Lost connection to server.")
                game_active = False
                window.destroy()

    buttons = []
    for i in range(9):
        btn = tk.Button(window, text='', width=10, height=4, font=('Arial', 12),
                        command=lambda idx=i: click(idx), bg='#ffffff', activebackground='#d9d9d9')
        btn.grid(row=i//3, column=i%3, padx=5, pady=5)
        buttons.append(btn)

    status_label = tk.Label(window, text=f"Your turn ({current_player})" if my_turn else f"{opponent_username}'s turn",
                            font=('Arial', 12), bg='#f0f0f0')
    status_label.grid(row=3, column=0, columnspan=3, pady=10)

    threading.Thread(target=receive_game_updates, daemon=True).start()
    logger.info(f"Game window launched for {initiator_username} vs {opponent_username}")
    return window