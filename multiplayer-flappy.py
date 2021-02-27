import random
import sys
import pygame
import socket
import time

from _thread import *
from pygame.locals import *
from datetime import datetime
from itertools import cycle

broadcast_port = 8080
HOST = ''
my_send_tcp_port = 0
my_rcv_tcp_port = 0
my_player_id = 0
players_count = 1
isMyTimeout = False
someoneTimedOut = False
noOneTimedOut = False
receivedAll = False
lost = False
otherScores = []
send_connections = []
rcv_connections = []
scores = []
my_score = 0

FPS = 30
SCREENWIDTH = 288
SCREENHEIGHT = 512
PIPEGAPSIZE = 100  # gap between upper and lower part of pipe
BASEY = SCREENHEIGHT * 0.79
# image, sound and hitmask  dicts
IMAGES, SOUNDS, HITMASKS = {}, {}, {}

# list of all possible players (tuple of 3 positions of flap)
PLAYERS_LIST = (
    # red bird
    (
        'assets/sprites/redbird-upflap.png',
        'assets/sprites/redbird-midflap.png',
        'assets/sprites/redbird-downflap.png',
    ),
    # blue bird
    (
        'assets/sprites/bluebird-upflap.png',
        'assets/sprites/bluebird-midflap.png',
        'assets/sprites/bluebird-downflap.png',
    ),
    # yellow bird
    (
        'assets/sprites/yellowbird-upflap.png',
        'assets/sprites/yellowbird-midflap.png',
        'assets/sprites/yellowbird-downflap.png',
    ),
)

# list of backgrounds
BACKGROUNDS_LIST = (
    'assets/sprites/background-day.png',
    'assets/sprites/background-night.png',
)

# list of pipes
PIPES_LIST = (
    'assets/sprites/pipe-green.png',
    'assets/sprites/pipe-red.png',
)

try:
    xrange
except NameError:
    xrange = range


def main():
    global SCREEN, FPSCLOCK
    pygame.init()
    FPSCLOCK = pygame.time.Clock()
    SCREEN = pygame.display.set_mode((SCREENWIDTH, SCREENHEIGHT))
    pygame.display.set_caption('Flappy Bird')

    # global variables
    global my_send_tcp_port, my_rcv_tcp_port, my_player_id, HOST, players_count

    HOST = socket.gethostbyname_ex('')[-1][-1]
    print("my ip-address: ", HOST)
    # set my send and receive port numbers and player id randomly
    random.seed(datetime.now())
    my_send_tcp_port = random.randint(2 ** 10, 2 ** 16)
    my_rcv_tcp_port = random.randint(2 ** 10, 2 ** 16)
    my_player_id = random.randint(10, 100)

    start_new_thread(listen_thread, ())
    start_new_thread(peer_discovery_thread, ())

    # numbers sprites for score display
    IMAGES['numbers'] = (
        pygame.image.load('assets/sprites/0.png').convert_alpha(),
        pygame.image.load('assets/sprites/1.png').convert_alpha(),
        pygame.image.load('assets/sprites/2.png').convert_alpha(),
        pygame.image.load('assets/sprites/3.png').convert_alpha(),
        pygame.image.load('assets/sprites/4.png').convert_alpha(),
        pygame.image.load('assets/sprites/5.png').convert_alpha(),
        pygame.image.load('assets/sprites/6.png').convert_alpha(),
        pygame.image.load('assets/sprites/7.png').convert_alpha(),
        pygame.image.load('assets/sprites/8.png').convert_alpha(),
        pygame.image.load('assets/sprites/9.png').convert_alpha()
    )

    # game over sprite
    IMAGES['gameover'] = pygame.image.load('assets/sprites/gameover.png').convert_alpha()
    # message sprite for welcome screen
    IMAGES['message'] = pygame.image.load('assets/sprites/message.png').convert_alpha()
    # base (ground) sprite
    IMAGES['base'] = pygame.image.load('assets/sprites/base.png').convert_alpha()

    # sounds
    if 'win' in sys.platform:
        soundExt = '.wav'
    else:
        soundExt = '.ogg'

    SOUNDS['die'] = pygame.mixer.Sound('assets/audio/die' + soundExt)
    SOUNDS['hit'] = pygame.mixer.Sound('assets/audio/hit' + soundExt)
    SOUNDS['point'] = pygame.mixer.Sound('assets/audio/point' + soundExt)
    SOUNDS['swoosh'] = pygame.mixer.Sound('assets/audio/swoosh' + soundExt)
    SOUNDS['wing'] = pygame.mixer.Sound('assets/audio/wing' + soundExt)

    # the first player who starts counting time will send the timeout message
    start_new_thread(timeout_thread, ())
    while True:
        # select random background sprites
        randBg = random.randint(0, len(BACKGROUNDS_LIST) - 1)
        IMAGES['background'] = pygame.image.load(BACKGROUNDS_LIST[randBg]).convert()

        # select random player sprites
        randPlayer = random.randint(0, len(PLAYERS_LIST) - 1)
        IMAGES['player'] = (
            pygame.image.load(PLAYERS_LIST[randPlayer][0]).convert_alpha(),
            pygame.image.load(PLAYERS_LIST[randPlayer][1]).convert_alpha(),
            pygame.image.load(PLAYERS_LIST[randPlayer][2]).convert_alpha(),
        )

        # select random pipe sprites
        pipeindex = random.randint(0, len(PIPES_LIST) - 1)
        IMAGES['pipe'] = (
            pygame.transform.flip(
                pygame.image.load(PIPES_LIST[pipeindex]).convert_alpha(), False, True),
            pygame.image.load(PIPES_LIST[pipeindex]).convert_alpha(),
        )

        # hismask for pipes
        HITMASKS['pipe'] = (
            getHitmask(IMAGES['pipe'][0]),
            getHitmask(IMAGES['pipe'][1]),
        )

        # hitmask for player
        HITMASKS['player'] = (
            getHitmask(IMAGES['player'][0]),
            getHitmask(IMAGES['player'][1]),
            getHitmask(IMAGES['player'][2]),
        )

        if players_count > 2:
            movementInfo = showWelcomeAnimation()

            crashInfo = mainGame(movementInfo)
            showGameOverScreen(crashInfo)


def timeout_thread():
    global isMyTimeOut, my_score, lost
    # a game is 60 seconds
    time.sleep(30)
    isMyTimeOut = True
    # todo: send timeout message to all players
    if not lost:
        send_score(my_score, send_timeout=True)


def showWelcomeAnimation():
    """Shows welcome screen animation of flappy bird"""
    # index of player to blit on screen
    playerIndex = 0
    playerIndexGen = cycle([0, 1, 2, 1])
    # iterator used to change playerIndex after every 5th iteration
    loopIter = 0

    playerx = int(SCREENWIDTH * 0.2)
    playery = int((SCREENHEIGHT - IMAGES['player'][0].get_height()) / 2)

    messagex = int((SCREENWIDTH - IMAGES['message'].get_width()) / 2)
    messagey = int(SCREENHEIGHT * 0.12)

    basex = 0
    # amount by which base can maximum shift to left
    baseShift = IMAGES['base'].get_width() - IMAGES['background'].get_width()

    # player shm for up-down motion on welcome screen
    playerShmVals = {'val': 0, 'dir': 1}

    while True:
        for event in pygame.event.get():
            if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_UP):
                # make first flap sound and return values for mainGame
                SOUNDS['wing'].play()
                return {
                    'playery': playery + playerShmVals['val'],
                    'basex': basex,
                    'playerIndexGen': playerIndexGen,
                }

        # adjust playery, playerIndex, basex
        if (loopIter + 1) % 5 == 0:
            playerIndex = next(playerIndexGen)
        loopIter = (loopIter + 1) % 30
        basex = -((-basex + 4) % baseShift)
        playerShm(playerShmVals)

        # draw sprites
        SCREEN.blit(IMAGES['background'], (0, 0))
        SCREEN.blit(IMAGES['player'][playerIndex],
                    (playerx, playery + playerShmVals['val']))
        SCREEN.blit(IMAGES['message'], (messagex, messagey))
        SCREEN.blit(IMAGES['base'], (basex, BASEY))

        pygame.display.update()
        FPSCLOCK.tick(FPS)


def mainGame(movementInfo):
    score = playerIndex = loopIter = 0
    playerIndexGen = movementInfo['playerIndexGen']
    playerx, playery = int(SCREENWIDTH * 0.2), movementInfo['playery']

    basex = movementInfo['basex']
    baseShift = IMAGES['base'].get_width() - IMAGES['background'].get_width()

    # get 2 new pipes to add to upperPipes lowerPipes list
    newPipe1 = getRandomPipe()
    newPipe2 = getRandomPipe()

    # list of upper pipes
    upperPipes = [
        {'x': SCREENWIDTH + 200, 'y': newPipe1[0]['y']},
        {'x': SCREENWIDTH + 200 + (SCREENWIDTH / 2), 'y': newPipe2[0]['y']},
    ]

    # list of lowerpipe
    lowerPipes = [
        {'x': SCREENWIDTH + 200, 'y': newPipe1[1]['y']},
        {'x': SCREENWIDTH + 200 + (SCREENWIDTH / 2), 'y': newPipe2[1]['y']},
    ]

    pipeVelX = -4

    # player velocity, max velocity, downward accleration, accleration on flap
    playerVelY = -9  # player's velocity along Y, default same as playerFlapped
    playerMaxVelY = 10  # max vel along Y, max descend speed
    playerMinVelY = -8  # min vel along Y, max ascend speed
    playerAccY = 1  # players downward accleration
    playerRot = 45  # player's rotation
    playerVelRot = 3  # angular speed
    playerRotThr = 20  # rotation threshold
    playerFlapAcc = -9  # players speed on flapping
    playerFlapped = False  # True when player flaps

    while True:
        for event in pygame.event.get():
            if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_UP):
                if playery > -2 * IMAGES['player'][0].get_height():
                    playerVelY = playerFlapAcc
                    playerFlapped = True
                    SOUNDS['wing'].play()

        # check for crash here
        crashTest = checkCrash({'x': playerx, 'y': playery, 'index': playerIndex},
                               upperPipes, lowerPipes)
        if crashTest[0]:
            return {
                'y': playery,
                'groundCrash': crashTest[1],
                'basex': basex,
                'upperPipes': upperPipes,
                'lowerPipes': lowerPipes,
                'score': score,
                'playerVelY': playerVelY,
                'playerRot': playerRot
            }

        # check for score
        playerMidPos = playerx + IMAGES['player'][0].get_width() / 2
        for pipe in upperPipes:
            pipeMidPos = pipe['x'] + IMAGES['pipe'][0].get_width() / 2
            if pipeMidPos <= playerMidPos < pipeMidPos + 4:
                score += 1
                global my_score
                my_score = score
                SOUNDS['point'].play()

        # playerIndex basex change
        if (loopIter + 1) % 3 == 0:
            playerIndex = next(playerIndexGen)
        loopIter = (loopIter + 1) % 30
        basex = -((-basex + 100) % baseShift)

        # rotate the player
        if playerRot > -90:
            playerRot -= playerVelRot

        # player's movement
        if playerVelY < playerMaxVelY and not playerFlapped:
            playerVelY += playerAccY
        if playerFlapped:
            playerFlapped = False

            # more rotation to cover the threshold (calculated in visible rotation)
            playerRot = 45

        playerHeight = IMAGES['player'][playerIndex].get_height()
        playery += min(playerVelY, BASEY - playery - playerHeight)

        # move pipes to left
        for uPipe, lPipe in zip(upperPipes, lowerPipes):
            uPipe['x'] += pipeVelX
            lPipe['x'] += pipeVelX

        # add new pipe when first pipe is about to touch left of screen
        if 0 < upperPipes[0]['x'] < 5:
            newPipe = getRandomPipe()
            upperPipes.append(newPipe[0])
            lowerPipes.append(newPipe[1])

        # remove first pipe if its out of the screen
        if upperPipes[0]['x'] < -IMAGES['pipe'][0].get_width():
            upperPipes.pop(0)
            lowerPipes.pop(0)

        # draw sprites
        SCREEN.blit(IMAGES['background'], (0, 0))

        for uPipe, lPipe in zip(upperPipes, lowerPipes):
            SCREEN.blit(IMAGES['pipe'][0], (uPipe['x'], uPipe['y']))
            SCREEN.blit(IMAGES['pipe'][1], (lPipe['x'], lPipe['y']))

        SCREEN.blit(IMAGES['base'], (basex, BASEY))
        # print score so player overlaps the score
        showScore(score)

        show_win_lose()

        # Player rotation has a threshold
        visibleRot = playerRotThr
        if playerRot <= playerRotThr:
            visibleRot = playerRot

        playerSurface = pygame.transform.rotate(IMAGES['player'][playerIndex], visibleRot)
        SCREEN.blit(playerSurface, (playerx, playery))

        pygame.display.update()
        FPSCLOCK.tick(FPS)


def showGameOverScreen(crashInfo):
    """crashes the player down ans shows gameover image"""
    score = crashInfo['score']
    playerx = SCREENWIDTH * 0.2
    playery = crashInfo['y']
    playerHeight = IMAGES['player'][0].get_height()
    playerVelY = crashInfo['playerVelY']
    playerAccY = 2
    playerRot = crashInfo['playerRot']
    playerVelRot = 7

    basex = crashInfo['basex']

    upperPipes, lowerPipes = crashInfo['upperPipes'], crashInfo['lowerPipes']

    # play hit and die sounds
    SOUNDS['hit'].play()
    if not crashInfo['groundCrash']:
        send_score(score)
        SOUNDS['die'].play()
        global lost
        lost = True

    while True:
        for event in pygame.event.get():
            if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_UP):
                if playery + playerHeight >= BASEY - 1:
                    return

        # player y shift
        if playery + playerHeight < BASEY - 1:
            playery += min(playerVelY, BASEY - playery - playerHeight)

        # player velocity change
        if playerVelY < 15:
            playerVelY += playerAccY

        # rotate only when it's a pipe crash
        if not crashInfo['groundCrash']:
            if playerRot > -90:
                playerRot -= playerVelRot

        # draw sprites
        SCREEN.blit(IMAGES['background'], (0, 0))

        for uPipe, lPipe in zip(upperPipes, lowerPipes):
            SCREEN.blit(IMAGES['pipe'][0], (uPipe['x'], uPipe['y']))
            SCREEN.blit(IMAGES['pipe'][1], (lPipe['x'], lPipe['y']))

        SCREEN.blit(IMAGES['base'], (basex, BASEY))
        showScore(score)

        # todo show win lose here
        show_win_lose()

        playerSurface = pygame.transform.rotate(IMAGES['player'][1], playerRot)
        SCREEN.blit(playerSurface, (playerx, playery))
        SCREEN.blit(IMAGES['gameover'], (50, 180))

        FPSCLOCK.tick(FPS)
        pygame.display.update()


def playerShm(playerShm):
    """oscillates the value of playerShm['val'] between 8 and -8"""
    if abs(playerShm['val']) == 8:
        playerShm['dir'] *= -1

    if playerShm['dir'] == 1:
        playerShm['val'] += 1
    else:
        playerShm['val'] -= 1


def getRandomPipe():
    """returns a randomly generated pipe"""
    # y of gap between upper and lower pipe
    gapY = random.randrange(0, int(BASEY * 0.6 - PIPEGAPSIZE))
    gapY += int(BASEY * 0.2)
    pipeHeight = IMAGES['pipe'][0].get_height()
    pipeX = SCREENWIDTH + 10

    return [
        {'x': pipeX, 'y': gapY - pipeHeight},  # upper pipe
        {'x': pipeX, 'y': gapY + PIPEGAPSIZE},  # lower pipe
    ]


def showScore(score):
    """displays score in center of screen"""
    scoreDigits = [int(x) for x in list(str(score))]
    totalWidth = 0  # total width of all numbers to be printed

    for digit in scoreDigits:
        totalWidth += IMAGES['numbers'][digit].get_width()

    Xoffset = (SCREENWIDTH - totalWidth) / 2

    for digit in scoreDigits:
        SCREEN.blit(IMAGES['numbers'][digit], (Xoffset, SCREENHEIGHT * 0.1))
        Xoffset += IMAGES['numbers'][digit].get_width()


def checkCrash(player, upperPipes, lowerPipes):
    """returns True if player collders with base or pipes."""
    pi = player['index']
    player['w'] = IMAGES['player'][0].get_width()
    player['h'] = IMAGES['player'][0].get_height()

    # if player crashes into ground
    if player['y'] + player['h'] >= BASEY - 1:
        return [True, True]
    else:

        playerRect = pygame.Rect(player['x'], player['y'],
                                 player['w'], player['h'])
        pipeW = IMAGES['pipe'][0].get_width()
        pipeH = IMAGES['pipe'][0].get_height()

        for uPipe, lPipe in zip(upperPipes, lowerPipes):
            # upper and lower pipe rects
            uPipeRect = pygame.Rect(uPipe['x'], uPipe['y'], pipeW, pipeH)
            lPipeRect = pygame.Rect(lPipe['x'], lPipe['y'], pipeW, pipeH)

            # player and upper/lower pipe hitmasks
            pHitMask = HITMASKS['player'][pi]
            uHitmask = HITMASKS['pipe'][0]
            lHitmask = HITMASKS['pipe'][1]

            # if bird collided with upipe or lpipe
            uCollide = pixelCollision(playerRect, uPipeRect, pHitMask, uHitmask)
            lCollide = pixelCollision(playerRect, lPipeRect, pHitMask, lHitmask)

            if uCollide or lCollide:
                return [True, False]

    return [False, False]


def pixelCollision(rect1, rect2, hitmask1, hitmask2):
    """Checks if two objects collide and not just their rects"""
    rect = rect1.clip(rect2)

    if rect.width == 0 or rect.height == 0:
        return False

    x1, y1 = rect.x - rect1.x, rect.y - rect1.y
    x2, y2 = rect.x - rect2.x, rect.y - rect2.y

    for x in xrange(rect.width):
        for y in xrange(rect.height):
            if hitmask1[x1 + x][y1 + y] and hitmask2[x2 + x][y2 + y]:
                return True
    return False


def getHitmask(image):
    """returns a hitmask using an image's alpha."""
    mask = []
    for x in xrange(image.get_width()):
        mask.append([])
        for y in xrange(image.get_height()):
            mask[x].append(bool(image.get_at((x, y))[3]))
    return mask


def peer_discovery_thread():
    # global variables
    global broadcast_port, my_send_tcp_port, my_rcv_tcp_port, my_player_id, players_count
    global send_connections, rcv_connections, HOST

    # create a UDP socket for broadcasting, let it reuse the port number and turn on broadcasts
    my_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    my_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # todo: ip address used here
    my_udp_socket.bind((HOST, broadcast_port))

    broadcast_msg = "broadcast ==> player: " + str(my_player_id) + " send to me on port " + str(my_rcv_tcp_port)
    broadcast_msg += " and receive from me on port " + str(my_send_tcp_port)

    # first thing a player will send a broadcast message to all other players on the network
    my_udp_socket.sendto(broadcast_msg.encode(), ('255.255.255.255', broadcast_port))
    print("SENT MESSAGE: ", broadcast_msg)

    # then the player will keep receiving from other players either their broadcast message or their confirmation
    # message to his broadcast. if he receives a broadcast message from other player he'll send a confirmation
    # back and try to start the tcp connections. else, if he receives a confirmation then there must be some
    # other player(s) who received his broadcast message and is/are trying to connect to him
    while True:
        received_msg, address = my_udp_socket.recvfrom(4096)
        received_msg = str(received_msg.decode())

        # ignore if the message is a broadcast from yourself
        if str(my_player_id) not in received_msg.split()[3]:
            print("RECEIVED MESSAGE: ", received_msg)
            print("FROM: ", address)

            # if it's a broadcast message from another player send a confirmation and request tcp connections from
            # him
            if "broadcast" in received_msg:
                other_player_id = int(received_msg.split()[3])
                other_player_ip = address[0]
                other_player_rcv_port = int(received_msg.split()[-8])
                other_player_send_port = int(received_msg.split()[-1])

                # send a confirmation back
                confirmation_msg = "confirmation ==> player: " + str(my_player_id) + " confirms receipt to "
                confirmation_msg += str(other_player_id)
                my_udp_socket.sendto(confirmation_msg.encode(), ('<broadcast>', broadcast_port))
                print("SENT CONFIRMATION")

                # create two sockets one for sending and one for receiving
                my_send_tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                my_rcv_tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                # send to the other player's receive port and receive from the other player's send port
                print("send connection requested from: ", (other_player_ip, other_player_rcv_port))
                my_send_tcp_socket.connect((other_player_ip, other_player_rcv_port))
                print("receive connection requested from: ", (other_player_ip, other_player_send_port))
                my_rcv_tcp_socket.connect((other_player_ip, other_player_send_port))

                # append to the saved connections
                send_connections.append(my_send_tcp_socket)
                rcv_connections.append(my_rcv_tcp_socket)

                print("connections established with player " + str(other_player_id))
                players_count += 1
                print("players count: ", players_count)

            elif "confirmation" in received_msg and str(my_player_id) in received_msg.split()[-1]:
                # if it's a confirmation message from another player to me then listen for connection requests
                # listen for the other player tcp connection request
                print("received confirmation")


def listen_thread():
    global HOST, players_count, send_connections, rcv_connections

    # create two sockets one for sending and one for receiving
    my_send_tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    my_rcv_tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # listen for connection requests maximum 9 other players
    # todo: ip address used here
    my_rcv_tcp_socket.bind((HOST, my_rcv_tcp_port))
    my_rcv_tcp_socket.listen(5)
    my_send_tcp_socket.bind((HOST, my_send_tcp_port))
    my_send_tcp_socket.listen(5)

    while True:
        # other player will send you on your receive port
        other_rcv_conn, other_player_rcv_addr = my_rcv_tcp_socket.accept()
        print("receive connection granted to: ", other_player_rcv_addr)
        rcv_connections.append(other_rcv_conn)

        # other player will receive from your send port
        other_send_conn, other_player_send_addr = my_send_tcp_socket.accept()
        print("send connection granted to: ", other_player_send_addr)
        send_connections.append(other_send_conn)

        players_count += 1
        print("players count: ", players_count)


def send_score(score, send_timeout=False):
    global send_connections, someoneTimedOut

    try:
        if not someoneTimedOut:
            if not send_timeout:
                msg = "score: " + str(score)
                for send_connection in send_connections:
                    send_connection.send(msg.encode())
                print("I sent a message to all")
            else:
                msg = "(timeout) score: " + str(score)
                for send_connection in send_connections:
                    send_connection.send(msg.encode())
                print("I sent a timeout to all")
    except socket.error:
        print("send score socket disconnected")


def get_scores_thread():
    global rcv_connections, someoneTimedOut, noOneTimedOut, receivedAll
    local_boolean = False  # to finish receiving from all

    for rcv_connection in rcv_connections:
        message = rcv_connection.recv(1024).decode()
        print("received message: ", message)
        scores.append(int(message.split()[-1]))
        if "(timeout)" in message:
            local_boolean = False

    someoneTimedOut = local_boolean
    receivedAll = True
    print("I received from all players")
    if not someoneTimedOut:
        noOneTimedOut = True
    else:
        print("I received a timeout")


def show_win_lose():
    global receivedAll, my_score
    if receivedAll:
        if my_score >= max(scores):
            SCREEN.blit(IMAGES['winner'], (50, 180))
        else:
            SCREEN.blit(IMAGES['loser'], (50, 180))


if __name__ == '__main__':
    main()
