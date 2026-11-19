import math
import random
import time

import chess

try:
    from .evaluate import evaluate
except ImportError:
    from evaluate import evaluate


class Node:
    def __init__(self, board: chess.Board, move=None, parent=None, player_just_moved=None):
        self.board = board.copy(stack=True)
        self.move = move
        self.parent = parent
        self.children = []
        self.visits = 0
        self.wins = 0.0
        self.untried_moves = list(self.board.legal_moves)
        self.player_just_moved = player_just_moved
        self.depth = 0 if parent is None else parent.depth + 1

    def init(self, board: chess.Board, move=None, parent=None, player_just_moved=None):
        self.__init__(board, move=move, parent=parent, player_just_moved=player_just_moved)


def _ucb1(child: Node, parent_visits: int, c: float) -> float:
    """UCB1 公式实现。"""
    if child.visits == 0:
        return float("inf")
    if parent_visits <= 0:
        return child.wins / child.visits
    return child.wins / child.visits + c * math.sqrt(math.log(parent_visits) / child.visits)


def _select(node: Node, c: float) -> Node:
    """选择阶段：沿着树往下找。"""
    while node.children and not node.board.is_game_over(claim_draw=True) and not node.untried_moves:
        node = max(node.children, key=lambda child: _ucb1(child, node.visits, c))
    return node


def _expand(node: Node) -> Node:
    """扩展阶段：添加一个新子节点。"""
    if not node.untried_moves:
        return node
    move = node.untried_moves.pop(random.randrange(len(node.untried_moves)))
    next_board = node.board.copy(stack=True)
    next_board.push(move)
    child = Node(
        next_board,
        move=move,
        parent=node,
        player_just_moved=not next_board.turn,
    )
    node.children.append(child)
    return child


def _terminal_score(board: chess.Board, root_player: bool) -> float:
    """终局计分。"""
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return 0.0
    return 1.0 if outcome.winner == root_player else -1.0


def _truncated_score(board: chess.Board, root_player: bool) -> float:
    """截断计分：用 evaluate 评估后转换为 root_player 视角的 [-1, 1]。"""
    score = evaluate(board)
    if board.turn == root_player:
        root_score = score
    else:
        root_score = -score
    if root_score > 0:
        return min(1.0, root_score / 100000.0)
    if root_score < 0:
        return max(-1.0, root_score / 100000.0)
    return 0.0


def _rollout(board: chess.Board, root_player: bool, rollout_limit: int) -> float:
    """模拟阶段：随机下棋到终局或步数上限。"""
    sim_board = board.copy(stack=True)
    for _ in range(max(0, rollout_limit)):
        if sim_board.is_game_over(claim_draw=True):
            return _terminal_score(sim_board, root_player)
        legal_moves = list(sim_board.legal_moves)
        if not legal_moves:
            return _terminal_score(sim_board, root_player)
        sim_board.push(random.choice(legal_moves))
    if sim_board.is_game_over(claim_draw=True):
        return _terminal_score(sim_board, root_player)
    return _truncated_score(sim_board, root_player)


def _backpropagate(node: Node, result: float, root_player: bool) -> None:
    """把根视角 [-1,1] 奖励转换为刚走棋方视角 [0,1]。"""
    root_reward = (1.0 + max(-1.0, min(1.0, float(result)))) / 2.0
    current = node
    while current is not None:
        current.visits += 1
        if current.player_just_moved is None:
            reward = root_reward
        elif current.player_just_moved == root_player:
            reward = root_reward
        else:
            reward = 1.0 - root_reward
        current.wins += reward
        current = current.parent


def choose_move(
    board: chess.Board,
    time_limit: float = 3.0,
    rollout_limit: int = 20,
    c: float = 1.41,
) -> chess.Move:
    """
    返回一个合法走法；不修改传入 board。
    UCB1: w/n + c * sqrt(ln(N)/n)
    最终选择：访问次数 visits 最多的子节点。
    rollout 截断时用 evaluate 打分。
    """
    if board.is_game_over(claim_draw=True):
        raise ValueError("cannot choose move for finished game")

    legal_moves = list(board.legal_moves)
    if not legal_moves:
        raise ValueError("no legal moves available")

    root = Node(board, player_just_moved=None)
    root_player = board.turn
    deadline = time.perf_counter() + max(0.0, time_limit)

    while time.perf_counter() < deadline:
        node = _select(root, c)
        if not node.board.is_game_over(claim_draw=True) and node.untried_moves:
            node = _expand(node)
        result = _rollout(node.board, root_player, rollout_limit)
        _backpropagate(node, result, root_player)

    if not root.children:
        return random.choice(legal_moves)

    best_child = max(root.children, key=lambda child: child.visits)
    return best_child.move