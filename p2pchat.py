import curses
import socket
import threading
import queue
import time
import sys
import atexit
from datetime import datetime
 
PORT = 12345
BROADCAST_ADDR = '255.255.255.255'
msg_queue = queue.Queue()
own_messages = set()
screen_refresh_event = threading.Event()
 
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
udp_sock.bind(('', PORT))
 
def cleanup():
    udp_sock.close()
atexit.register(cleanup)
 
def network_receiver():
    while True:
        try:
            data, addr = udp_sock.recvfrom(1024)
            msg = data.decode('utf-8', errors='ignore').strip()
            if msg and msg not in own_messages:
                msg_queue.put(msg)
                screen_refresh_event.set()
        except Exception:
            time.sleep(0.1)
 
def chat_app(stdscr):
    curses.curs_set(0)
    curses.cbreak()
    curses.noecho()
    stdscr.nodelay(True)
    stdscr.keypad(True)
    curses.start_color()
    curses.use_default_colors()
 
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    curses.init_pair(5, curses.COLOR_WHITE, -1)
 
    stdscr.addstr(0, 0, "Welcome to P2P Chat!", curses.color_pair(1) | curses.A_BOLD)
    stdscr.addstr(2, 0, "Enter your username: ", curses.color_pair(2) | curses.A_BOLD)
    stdscr.refresh()
 
    curses.echo()
    stdscr.nodelay(False)
    username = stdscr.getstr(2, 24, 30).decode('utf-8').strip()
    if not username:
        username = f"User_{int(time.time()) % 10000}"
    stdscr.nodelay(True)
    curses.noecho()
 
    # ── FIX 1: clear & fully rebuild the UI immediately after username entry ──
    stdscr.clear()
    stdscr.refresh()
 
    h, w = stdscr.getmaxyx()
    header_h = 3
 
    info = f" P2P CHAT | User: {username}"
    stdscr.addstr(0, 0, info.center(w-1), curses.color_pair(2) | curses.A_BOLD)
    stdscr.addstr(1, 0, "=" * (w-1), curses.color_pair(5))
    stdscr.refresh()
 
    msg_h = max(5, h - header_h - 5)
    msg_win = curses.newwin(msg_h, w, header_h + 1, 0)
    msg_win.scrollok(True)
    msg_win.idlok(True)
 
    input_win = curses.newwin(3, w, h - 3, 0)
    input_win.border()
    # ── FIX 2: removed Ctrl+Z (^Z) from the label, only Ctrl+D remains ──
    input_win.addstr(0, 2, " MESSAGE INPUT (Ctrl+D to Quit) ", curses.color_pair(4) | curses.A_BOLD)
    input_win.addstr(1, 1, "> ", curses.color_pair(2) | curses.A_BOLD)
 
    msg_win.refresh()
    input_win.refresh()
    stdscr.refresh()
 
    input_buf = ""
    input_scroll = 0
 
    def update_input():
        nonlocal input_scroll
        input_win.erase()
        input_win.border()
        input_win.addstr(0, 2, " MESSAGE INPUT (Ctrl+D to Quit) ", curses.color_pair(4) | curses.A_BOLD)
        input_win.addstr(1, 1, "> ", curses.color_pair(2) | curses.A_BOLD)
 
        max_visible = w - 4
        if len(input_buf) > max_visible:
            if input_scroll > len(input_buf) - max_visible:
                input_scroll = len(input_buf) - max_visible
            if input_scroll < 0:
                input_scroll = 0
            display_buf = input_buf[input_scroll:input_scroll + max_visible]
        else:
            display_buf = input_buf
            input_scroll = 0
 
        input_win.addstr(1, 3, display_buf)
        input_win.refresh()
 
    def print_msg(text):
        max_len = w - 2
        while len(text) > max_len:
            split_at = text[:max_len].rfind(' ')
            if split_at == -1: split_at = max_len
            msg_win.addstr(text[:split_at] + "\n")
            text = text[split_at:].lstrip()
        msg_win.addstr(text + "\n")
        msg_win.refresh()
        stdscr.refresh()
 
    def process_messages():
        processed = False
        while not msg_queue.empty():
            try:
                incoming = msg_queue.get_nowait()
                ts = datetime.now().strftime("%H:%M:%S")
                print_msg(f"[{ts}] {incoming}")
                processed = True
            except queue.Empty:
                break
        return processed
 
    threading.Thread(target=network_receiver, daemon=True).start()
 
    print_msg(f"[System] Welcome, {username}. Waiting for peers on LAN...")
    print_msg("[System] Type and press ENTER to send. Ctrl+D to exit.")
 
    while True:
        processed = process_messages()
 
        key = stdscr.getch()
 
        if key == -1:
            if processed:
                stdscr.refresh()
                screen_refresh_event.clear()
            else:
                screen_refresh_event.wait(timeout=0.05)
            continue
 
        if key in (10, 13, 271):
            if input_buf.strip():
                full_msg = f"[{username}]: {input_buf.strip()}"
                own_messages.add(full_msg)
                ts = datetime.now().strftime("%H:%M:%S")
                print_msg(f"[{ts}] {full_msg}")
                try:
                    udp_sock.sendto(full_msg.encode(), (BROADCAST_ADDR, PORT))
                except Exception as e:
                    print_msg(f"[System] Send error: {e}")
                    own_messages.discard(full_msg)
 
                if len(own_messages) > 100:
                    own_messages.clear()
 
                input_buf = ""
                input_scroll = 0
                update_input()
            continue
 
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if input_buf:
                input_buf = input_buf[:-1]
                if len(input_buf) < input_scroll:
                    input_scroll = len(input_buf)
                update_input()
            continue
 
        elif key == 4:  # Ctrl+D only
            print_msg("[System] Exiting...")
            time.sleep(0.2)
            break
 
        elif 32 <= key <= 126:
            input_buf += chr(key)
            if len(input_buf) - input_scroll > w - 4:
                input_scroll = len(input_buf) - (w - 4) + 1
            update_input()
            continue
 
        elif key == curses.KEY_LEFT:
            if input_scroll > 0:
                input_scroll -= 1
                update_input()
            continue
 
        elif key == curses.KEY_RIGHT:
            if input_scroll < len(input_buf) - (w - 4):
                input_scroll += 1
                update_input()
            continue
 
        elif key == curses.KEY_RESIZE:
            try:
                stdscr.clear()
                h, w = stdscr.getmaxyx()
                msg_win.resize(max(5, h - header_h - 5), w)
                msg_win.mvwin(header_h + 1, 0)
                input_win.resize(3, w)
                input_win.mvwin(h - 3, 0)
                msg_win.refresh()
                input_win.refresh()
                stdscr.refresh()
                update_input()
            except curses.error:
                pass
            continue
 
if __name__ == "__main__":
    try:
        curses.wrapper(chat_app)
    except KeyboardInterrupt:
        pass
    finally:
        curses.endwin()
        print("\nChat closed. Goodbye!")
 
