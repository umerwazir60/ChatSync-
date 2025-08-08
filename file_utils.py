import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def read_file_bytes(filepath):
    """Read a file and return its bytes."""
    try:
        with open(filepath, 'rb') as file:
            data = file.read()
            logger.info(f"Read file: {filepath} ({len(data)} bytes)")
            return data
    except Exception as e:
        logger.error(f"Unable to read file {filepath}: {e}")
        return None

def save_file_from_bytes(data, filename, save_dir="downloads"):
    """Save received bytes into a file, avoiding overwrites by appending a number."""
    try:
        os.makedirs(save_dir, exist_ok=True)
        base, ext = os.path.splitext(filename)
        full_path = os.path.join(save_dir, filename)
        counter = 1
        while os.path.exists(full_path):
            full_path = os.path.join(save_dir, f"{base}({counter}){ext}")
            counter += 1
        with open(full_path, 'wb') as file:
            file.write(data)
        logger.info(f"File saved: {full_path} ({len(data)} bytes)")
        return True
    except Exception as e:
        logger.error(f"Unable to save file {filename}: {e}")
        return False

def send_file(sock, filepath):
    """Send a file to the server using socket."""
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return False

    try:
        filename = os.path.basename(filepath)
        file_data = read_file_bytes(filepath)
        if file_data is None:
            return False

        header = f"/file:{filename}:{len(file_data)}"
        sock.send(header.encode('utf-8'))

        ack = sock.recv(1024).decode('utf-8')
        if ack == "READY":
            sock.sendall(file_data)
            logger.info(f"File sent: {filename} ({len(file_data)} bytes)")
            return True
        else:
            logger.error(f"Server not ready to receive file: {ack}")
            return False
    except Exception as e:
        logger.error(f"Failed to send file {filepath}: {e}")
        return False