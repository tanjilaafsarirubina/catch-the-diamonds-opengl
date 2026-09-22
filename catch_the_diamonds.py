"""
Catch the Diamonds!
===================

A small arcade game built with PyOpenGL + GLUT. Every shape on screen is
rasterised by hand with the Midpoint Line Algorithm (generalised to all
8 zones) and plotted with GL_POINTS only - no GL_LINES, no polygons.

Controls
--------
    Left / Right arrow      move the catcher
    C                       toggle cheat mode (catcher follows the diamond)
    Space / P               play / pause
    R                       restart
    Esc / Q                 quit

    Teal arrow  (top-left)    restart
    Amber icon  (top-centre)  play / pause
    Red cross   (top-right)   quit
"""

import os
import random
import sys
import time

from OpenGL.GL import *
from OpenGL.GLUT import *


# ---------------------------------------------------------------- settings --

WIN_W, WIN_H = 800, 750     # logical playfield size (pixels)
FRAME_MS     = 16           # update / redraw interval (~60 FPS)
MAX_DT       = 0.05         # clamp long frames (e.g. while dragging the window)
POINT_SIZE   = 2.0          # size of every plotted point at 1:1 scale

DIAMOND_W    = 22           # half-width of the diamond
DIAMOND_H    = 28           # half-height of the diamond

CATCHER_OW   = 62           # half-width of the catcher's top (opening) edge
CATCHER_IW   = 33           # half-width of the catcher's flat base
CATCHER_HT   = 26           # catcher height
CATCHER_YB   = 45           # y of the catcher's base

CATCH_SPD    = 320.0        # catcher speed (px/s) under player control
CHEAT_SPD    = 900.0        # catcher speed (px/s) in cheat mode
INIT_DSP     = 85.0         # initial diamond fall speed (px/s)
DSP_INC      = 14.0         # extra fall speed per diamond caught

# HUD bar along the top of the window
HUD_Y   = WIN_H - 68        # separator line between HUD and playfield
BTN_R   = 22                # button "radius" (half-size)
BTN_Y   = WIN_H - 40        # button y-centre
BTN1_X  = 55                # restart     (teal)
BTN2_X  = WIN_W // 2        # play/pause  (amber)
BTN3_X  = WIN_W - 55        # quit        (red)
BTN_HIT = BTN_R + 10        # clickable half-size around each button

# Seven-segment score, right-aligned just left of the quit button
DIGIT_W     = 14
DIGIT_H     = 28
DIGIT_GAP   = 8
SCORE_RIGHT = BTN3_X - BTN_HIT - 24

# Colours
BG_COLOR          = (0.06, 0.06, 0.13)
SEPARATOR_COLOR   = (0.22, 0.22, 0.32)
CATCHER_COLOR     = (1.0, 1.0, 1.0)
CATCHER_LOST      = (1.0, 0.0, 0.0)
RESTART_COLOR     = (0.0, 0.9, 0.8)
PLAYPAUSE_COLOR   = (1.0, 0.70, 0.0)
QUIT_COLOR        = (1.0, 0.15, 0.15)
SCORE_COLOR       = (0.85, 0.85, 0.95)
SCORE_CHEAT_COLOR = (1.0, 0.20, 1.0)

DIAMOND_COLORS = [
    (1.0,  0.20, 0.20),     # red
    (0.20, 1.0,  0.20),     # green
    (0.30, 0.75, 1.0),      # sky-blue
    (1.0,  1.0,  0.0),      # yellow
    (1.0,  0.20, 1.0),      # magenta
    (0.0,  1.0,  1.0),      # cyan
    (1.0,  0.55, 0.0),      # orange
    (0.55, 1.0,  0.0),      # lime
]


# ------------------------------------------------ midpoint line algorithm --
#
# The classic midpoint algorithm only handles zone 0 (0 <= slope <= 1,
# left to right). Any other line is mapped into zone 0, rasterised there,
# and every generated point is mapped back to its original zone.
#
#        \ 2 | 1 /
#       3  \ | /  0
#       -----+-----
#       4  / | \  7
#        / 5 | 6 \

def _zone(dx, dy):
    """Return which of the 8 zones the direction (dx, dy) falls in."""
    if abs(dx) >= abs(dy):
        if   dx >= 0 and dy >= 0: return 0
        elif dx <  0 and dy >= 0: return 3
        elif dx <  0 and dy <  0: return 4
        else:                     return 7   # dx >= 0, dy < 0
    else:
        if   dx >= 0 and dy >= 0: return 1
        elif dx <  0 and dy >= 0: return 2
        elif dx <  0 and dy <  0: return 5
        else:                     return 6   # dx >= 0, dy < 0


# Zone N -> zone 0
_TO0 = [
    lambda x, y: ( x,  y),   # 0 -> 0  identity
    lambda x, y: ( y,  x),   # 1 -> 0  swap
    lambda x, y: ( y, -x),   # 2 -> 0  swap + negate x
    lambda x, y: (-x,  y),   # 3 -> 0  negate x
    lambda x, y: (-x, -y),   # 4 -> 0  negate both
    lambda x, y: (-y, -x),   # 5 -> 0  swap + negate both
    lambda x, y: (-y,  x),   # 6 -> 0  swap + negate y
    lambda x, y: ( x, -y),   # 7 -> 0  negate y
]

# Zone 0 -> zone N (inverse of the table above)
_FR0 = [
    lambda x, y: ( x,  y),   # 0 <- 0  identity
    lambda x, y: ( y,  x),   # 1 <- 0  swap (self-inverse)
    lambda x, y: (-y,  x),   # 2 <- 0
    lambda x, y: (-x,  y),   # 3 <- 0  negate x (self-inverse)
    lambda x, y: (-x, -y),   # 4 <- 0  negate both (self-inverse)
    lambda x, y: (-y, -x),   # 5 <- 0  swap + negate (self-inverse)
    lambda x, y: ( y, -x),   # 6 <- 0
    lambda x, y: ( x, -y),   # 7 <- 0  negate y (self-inverse)
]


def draw_line(x1, y1, x2, y2):
    """Rasterise a line segment with the midpoint algorithm using GL_POINTS."""
    x1, y1 = int(round(x1)), int(round(y1))
    x2, y2 = int(round(x2)), int(round(y2))

    dx, dy = x2 - x1, y2 - y1

    if dx == 0 and dy == 0:
        glBegin(GL_POINTS)
        glVertex2f(x1, y1)
        glEnd()
        return

    z = _zone(dx, dy)
    ax1, ay1 = _TO0[z](x1, y1)
    ax2, ay2 = _TO0[z](x2, y2)

    if ax1 > ax2:
        ax1, ay1, ax2, ay2 = ax2, ay2, ax1, ay1

    ddx   = ax2 - ax1
    ddy   = ay2 - ay1
    d     = 2 * ddy - ddx
    incE  = 2 * ddy
    incNE = 2 * (ddy - ddx)
    y = ay1

    glBegin(GL_POINTS)
    for x in range(ax1, ax2 + 1):
        px, py = _FR0[z](x, y)
        glVertex2f(px, py)
        if d > 0:
            d += incNE
            y += 1
        else:
            d += incE
    glEnd()


# ------------------------------------------------------------------ shapes --

def draw_diamond(cx, cy, color):
    glColor3f(*color)
    w, h = DIAMOND_W, DIAMOND_H
    draw_line(cx,     cy + h, cx + w, cy    )   # top    -> right
    draw_line(cx + w, cy,     cx,     cy - h)   # right  -> bottom
    draw_line(cx,     cy - h, cx - w, cy    )   # bottom -> left
    draw_line(cx - w, cy,     cx,     cy + h)   # left   -> top


def draw_catcher(cx, color):
    glColor3f(*color)
    yb, yt = CATCHER_YB, CATCHER_YB + CATCHER_HT
    ow, iw = CATCHER_OW, CATCHER_IW
    draw_line(cx - ow, yt, cx + ow, yt)   # top bar (opening edge)
    draw_line(cx - ow, yt, cx - iw, yb)   # left diagonal wall
    draw_line(cx - iw, yb, cx + iw, yb)   # flat base
    draw_line(cx + iw, yb, cx + ow, yt)   # right diagonal wall


def draw_restart_button():
    """Left-pointing arrow."""
    glColor3f(*RESTART_COLOR)
    cx, cy, r = BTN1_X, BTN_Y, BTN_R
    head = r * 3 // 4
    draw_line(cx - r, cy, cx + r,        cy       )   # shaft
    draw_line(cx - r, cy, cx - r + head, cy + head)   # upper barb
    draw_line(cx - r, cy, cx - r + head, cy - head)   # lower barb


def draw_play_pause_button(paused):
    """Play triangle while paused, pause bars while running."""
    glColor3f(*PLAYPAUSE_COLOR)
    cx, cy, r = BTN2_X, BTN_Y, BTN_R
    if paused:
        draw_line(cx - r, cy + r, cx + r, cy    )
        draw_line(cx + r, cy,     cx - r, cy - r)
        draw_line(cx - r, cy - r, cx - r, cy + r)
    else:
        g = r // 3
        for x0, x1 in ((cx - r, cx - g), (cx + g, cx + r)):
            draw_line(x0, cy + r, x1, cy + r)
            draw_line(x1, cy + r, x1, cy - r)
            draw_line(x1, cy - r, x0, cy - r)
            draw_line(x0, cy - r, x0, cy + r)


def draw_quit_button():
    """Cross inside a box."""
    glColor3f(*QUIT_COLOR)
    cx, cy, r = BTN3_X, BTN_Y, BTN_R
    draw_line(cx - r, cy + r, cx + r, cy - r)   # diagonal \
    draw_line(cx - r, cy - r, cx + r, cy + r)   # diagonal /
    draw_line(cx - r, cy - r, cx + r, cy - r)   # box bottom
    draw_line(cx + r, cy - r, cx + r, cy + r)   # box right
    draw_line(cx + r, cy + r, cx - r, cy + r)   # box top
    draw_line(cx - r, cy + r, cx - r, cy - r)   # box left


def draw_separator():
    glColor3f(*SEPARATOR_COLOR)
    draw_line(0, HUD_Y, WIN_W, HUD_Y)


# Segments lit for each digit:
#      a
#    f   b
#      g
#    e   c
#      d
_SEGMENTS = {
    "0": "abcdef", "1": "bc",     "2": "abdeg", "3": "abcdg",   "4": "bcfg",
    "5": "acdfg",  "6": "acdefg", "7": "abc",   "8": "abcdefg", "9": "abcdfg",
}


def draw_digit(ch, x, y):
    """Seven-segment digit whose bottom-left corner is at (x, y)."""
    w, h = DIGIT_W, DIGIT_H
    m = y + h // 2
    ends = {
        "a": (x,     y + h, x + w, y + h),
        "b": (x + w, y + h, x + w, m    ),
        "c": (x + w, m,     x + w, y    ),
        "d": (x,     y,     x + w, y    ),
        "e": (x,     y,     x,     m    ),
        "f": (x,     m,     x,     y + h),
        "g": (x,     m,     x + w, m    ),
    }
    for seg in _SEGMENTS[ch]:
        draw_line(*ends[seg])


def draw_score(score, color):
    glColor3f(*color)
    text = str(score)
    step = DIGIT_W + DIGIT_GAP
    x = SCORE_RIGHT - len(text) * step + DIGIT_GAP
    y = BTN_Y - DIGIT_H // 2
    for ch in text:
        draw_digit(ch, x, y)
        x += step


# -------------------------------------------------------------- game state --

class Game:
    """All mutable game state plus the per-frame update logic."""

    def __init__(self):
        # Physical key state is tracked separately from game state so that a
        # key held across pause / restart / cheat-mode toggles keeps working.
        self.key_left  = False
        self.key_right = False
        self.last_t    = time.perf_counter()
        self.restart(announce=False)

    def restart(self, announce=True):
        self.score      = 0
        self.game_over  = False
        self.paused     = False
        self.cheat_mode = False
        self.diam_speed = INIT_DSP
        self.catch_x    = WIN_W / 2
        self.spawn_diamond()
        if announce:
            print("Starting Over")

    def spawn_diamond(self):
        """Drop a new diamond from just below the HUD at a random x."""
        self.diam_x     = float(random.randint(DIAMOND_W + 12, WIN_W - DIAMOND_W - 12))
        self.diam_y     = float(HUD_Y - DIAMOND_H - 4)
        self.diam_color = random.choice(DIAMOND_COLORS)

    def toggle_pause(self):
        if self.game_over:
            return
        self.paused = not self.paused
        print("Paused" if self.paused else "Resumed")

    def toggle_cheat(self):
        if self.game_over:
            return
        self.cheat_mode = not self.cheat_mode
        print(f"Cheat Mode {'ON' if self.cheat_mode else 'OFF'}")

    def update(self, dt):
        if self.game_over or self.paused:
            return

        if self.cheat_mode:
            diff = self.diam_x - self.catch_x
            step = CHEAT_SPD * dt
            if abs(diff) <= step:
                self.catch_x = self.diam_x
            else:
                self.catch_x += step if diff > 0 else -step
        else:
            direction = int(self.key_right) - int(self.key_left)
            self.catch_x += direction * CATCH_SPD * dt

        self.catch_x = min(max(self.catch_x, CATCHER_OW + 2), WIN_W - CATCHER_OW - 2)

        self.diam_y -= self.diam_speed * dt

        if self._diamond_in_catcher():
            self.score += 1
            print(f"Score: {self.score}")
            self.diam_speed = INIT_DSP + DSP_INC * self.score
            self.spawn_diamond()
        elif self.diam_y + DIAMOND_H < CATCHER_YB:
            self.game_over = True
            print(f"Game Over! Score: {self.score}")

    def _diamond_in_catcher(self):
        """Axis-aligned bounding-box test between the diamond and the catcher."""
        d_l, d_r = self.diam_x - DIAMOND_W,  self.diam_x + DIAMOND_W
        d_b, d_t = self.diam_y - DIAMOND_H,  self.diam_y + DIAMOND_H
        c_l, c_r = self.catch_x - CATCHER_OW, self.catch_x + CATCHER_OW
        c_b, c_t = CATCHER_YB,                CATCHER_YB + CATCHER_HT
        return d_l < c_r and d_r > c_l and d_b < c_t and d_t > c_b

    def draw(self):
        draw_separator()
        if not self.game_over:              # the diamond vanishes on game over
            draw_diamond(self.diam_x, self.diam_y, self.diam_color)
        draw_catcher(self.catch_x, CATCHER_LOST if self.game_over else CATCHER_COLOR)
        draw_restart_button()
        draw_play_pause_button(self.paused)
        draw_quit_button()
        draw_score(self.score, SCORE_CHEAT_COLOR if self.cheat_mode else SCORE_COLOR)


game = None

# Letterboxed viewport inside the window, updated on every resize.
_view = {"x": 0, "y": 0, "w": WIN_W, "h": WIN_H, "win_h": WIN_H, "point_size": POINT_SIZE}


# ----------------------------------------------------------- GLUT callbacks --

def display():
    glClear(GL_COLOR_BUFFER_BIT)
    glPointSize(_view["point_size"])
    game.draw()
    glutSwapBuffers()


def reshape(w, h):
    """Scale the playfield to the window while keeping its aspect ratio."""
    scale = min(w / WIN_W, h / WIN_H)
    vw = max(int(WIN_W * scale), 1)
    vh = max(int(WIN_H * scale), 1)
    vx, vy = (w - vw) // 2, (h - vh) // 2
    glViewport(vx, vy, vw, vh)
    _view.update(x=vx, y=vy, w=vw, h=vh, win_h=h,
                 point_size=max(1.0, POINT_SIZE * scale))


def tick(_value):
    now = time.perf_counter()
    dt = min(now - game.last_t, MAX_DT)
    game.last_t = now
    game.update(dt)
    glutPostRedisplay()
    glutTimerFunc(FRAME_MS, tick, 0)


def keyboard(key, _x, _y):
    key = key.lower()
    if key == b'c':
        game.toggle_cheat()
    elif key in (b' ', b'p'):
        game.toggle_pause()
    elif key == b'r':
        game.restart()
    elif key in (b'\x1b', b'q'):
        quit_game()


def special(key, _x, _y):
    if key == GLUT_KEY_LEFT:
        game.key_left = True
    elif key == GLUT_KEY_RIGHT:
        game.key_right = True


def special_up(key, _x, _y):
    if key == GLUT_KEY_LEFT:
        game.key_left = False
    elif key == GLUT_KEY_RIGHT:
        game.key_right = False


def _to_world(mx, my):
    """Convert window coordinates (origin top-left) to playfield coordinates."""
    v = _view
    x = (mx - v["x"]) * WIN_W / v["w"]
    y = (v["win_h"] - my - v["y"]) * WIN_H / v["h"]
    return x, y


def _on_button(x, y, bx):
    return abs(x - bx) < BTN_HIT and abs(y - BTN_Y) < BTN_HIT


def mouse(button, state, mx, my):
    if button != GLUT_LEFT_BUTTON or state != GLUT_DOWN:
        return
    x, y = _to_world(mx, my)
    if _on_button(x, y, BTN1_X):
        game.restart()
    elif _on_button(x, y, BTN2_X):
        game.toggle_pause()
    elif _on_button(x, y, BTN3_X):
        quit_game()


def quit_game():
    if glutLeaveMainLoop:           # freeglut: return from glutMainLoop()
        glutLeaveMainLoop()
    else:                           # classic GLUT (e.g. macOS) never returns
        print(f"Goodbye! Score: {game.score}")
        sys.stdout.flush()
        os._exit(0)


# -------------------------------------------------------------------- main --

def init_gl():
    glClearColor(*BG_COLOR, 1.0)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(0, WIN_W, 0, WIN_H, -1, 1)     # y = 0 at the bottom
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()


def create_window():
    glutInit(sys.argv)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB)
    glutInitWindowSize(WIN_W, WIN_H)
    glutInitWindowPosition(150, 80)
    glutCreateWindow(b"Catch the Diamonds!")
    if glutSetOption:               # freeglut: closing the window returns from the loop
        glutSetOption(GLUT_ACTION_ON_WINDOW_CLOSE, GLUT_ACTION_GLUTMAINLOOP_RETURNS)
    init_gl()


def main():
    global game

    create_window()
    game = Game()

    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutKeyboardFunc(keyboard)
    glutSpecialFunc(special)
    glutSpecialUpFunc(special_up)
    glutMouseFunc(mouse)
    glutIgnoreKeyRepeat(1)          # one down / one up event per key press
    glutTimerFunc(FRAME_MS, tick, 0)

    print("=== Catch the Diamonds! ===")
    print("Left/Right : move catcher     C : toggle cheat mode")
    print("Space / P  : play / pause     R : restart     Esc / Q : quit")
    print("Buttons    : teal arrow = restart, amber = play/pause, red X = quit")

    glutMainLoop()
    print(f"Goodbye! Score: {game.score}")


if __name__ == "__main__":
    main()
