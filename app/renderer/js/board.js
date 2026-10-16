/* Chessboard rendering: pieces, highlights, click-to-move and keyboard navigation. */
(function () {
    const FILES = 'abcdefgh';
    const NAMES = { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' };

    function pieceImage(symbol) {
        const color = symbol === symbol.toUpperCase() ? 'w' : 'b';
        return `../assets/pieces/${color}${symbol.toLowerCase()}.svg`;
    }

    function pieceLabel(symbol) {
        const color = symbol === symbol.toUpperCase() ? 'white' : 'black';
        return `${color} ${NAMES[symbol.toLowerCase()]}`;
    }

    class Board {
        constructor(element, { onMove, onAnnounce, promotionPicker }) {
            this.el = element;
            this.onMove = onMove;
            this.onAnnounce = onAnnounce || (() => {});
            this.picker = promotionPicker;
            this.state = null;
            this.selected = null;
            this.focusSquare = 'e2';
            this.buttons = {};
            this.build(false);
            this.el.addEventListener('keydown', (e) => this.onKey(e));
        }

        orderedSquares(flipped) {
            const squares = [];
            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    const file = flipped ? 7 - c : c;
                    const rank = flipped ? r + 1 : 8 - r;
                    squares.push(FILES[file] + rank);
                }
            }
            return squares;
        }

        build(flipped) {
            this.flipped = flipped;
            this.el.textContent = '';
            this.buttons = {};
            this.order = this.orderedSquares(flipped);
            this.order.forEach((sq, i) => {
                const file = FILES.indexOf(sq[0]);
                const rank = Number(sq[1]);
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'square ' + ((file + rank) % 2 === 0 ? 'dark' : 'light');
                button.dataset.square = sq;
                button.setAttribute('role', 'gridcell');
                button.tabIndex = -1;
                button.addEventListener('click', () => this.click(sq));
                if (i % 8 === 0) {
                    const r = document.createElement('span');
                    r.className = 'coord rank';
                    r.textContent = rank;
                    button.appendChild(r);
                }
                if (i >= 56) {
                    const f = document.createElement('span');
                    f.className = 'coord file';
                    f.textContent = sq[0];
                    button.appendChild(f);
                }
                this.el.appendChild(button);
                this.buttons[sq] = button;
            });
        }

        render(state) {
            const flipped = state.playerColor === 'black';
            if (flipped !== this.flipped) this.build(flipped);
            this.state = state;
            if (this.selected && !(state.legal[this.selected] || []).length) this.selected = null;
            this.hidePicker();

            for (const sq of this.order) {
                const button = this.buttons[sq];
                const symbol = state.pieces[sq];
                let img = button.querySelector('img.piece');
                if (symbol) {
                    if (!img) {
                        img = document.createElement('img');
                        img.className = 'piece';
                        img.alt = '';
                        img.draggable = false;
                        button.appendChild(img);
                    }
                    const src = pieceImage(symbol);
                    if (img.getAttribute('src') !== src) img.setAttribute('src', src);
                } else if (img) {
                    img.remove();
                }
                const targets = this.selected ? (state.legal[this.selected] || []) : [];
                button.classList.toggle('last', !!state.lastMove && (state.lastMove.from === sq || state.lastMove.to === sq));
                button.classList.toggle('selected', this.selected === sq);
                button.classList.toggle('target', targets.includes(sq));
                button.classList.toggle('capture-target', targets.includes(sq) && !!symbol);
                button.classList.toggle('check', state.check === sq);
                button.classList.toggle('movable', !!state.legal[sq]);
                button.setAttribute('aria-label', symbol ? `${sq}, ${pieceLabel(symbol)}` : `${sq}, empty`);
                button.setAttribute('aria-selected', this.selected === sq ? 'true' : 'false');
                button.tabIndex = sq === this.focusSquare ? 0 : -1;
            }
        }

        click(sq) {
            const state = this.state;
            this.focusSquare = sq;
            if (!state || !state.active || state.turn !== state.playerColor) return;
            const targets = this.selected ? (state.legal[this.selected] || []) : [];
            if (this.selected && targets.includes(sq)) {
                const from = this.selected;
                this.selected = null;
                const piece = state.pieces[from];
                const lastRank = state.playerColor === 'white' ? '8' : '1';
                if (piece && piece.toLowerCase() === 'p' && sq[1] === lastRank) {
                    this.render(state);
                    this.showPicker(from, sq);
                } else {
                    this.onMove(from, sq);
                    this.render(state);
                }
                return;
            }
            if (state.legal[sq]) {
                this.selected = this.selected === sq ? null : sq;
                if (this.selected) {
                    this.onAnnounce(`${pieceLabel(state.pieces[sq])} on ${sq} selected. Moves: ${state.legal[sq].join(', ')}.`);
                }
            } else {
                this.selected = null;
            }
            this.render(state);
        }

        showPicker(from, to) {
            const picker = this.picker;
            picker.textContent = '';
            const white = this.state.playerColor === 'white';
            ['q', 'r', 'b', 'n'].forEach((p) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.setAttribute('aria-label', `Promote to ${NAMES[p]}`);
                const img = document.createElement('img');
                img.src = pieceImage(white ? p.toUpperCase() : p);
                img.alt = '';
                b.appendChild(img);
                b.addEventListener('click', () => {
                    this.hidePicker();
                    this.onMove(from, to, p);
                });
                picker.appendChild(b);
            });
            picker.hidden = false;
            picker.firstChild.focus();
        }

        hidePicker() {
            this.picker.hidden = true;
        }

        onKey(e) {
            const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
            const d = moves[e.key];
            if (!d) return;
            e.preventDefault();
            const sign = this.flipped ? -1 : 1;
            const file = FILES.indexOf(this.focusSquare[0]) + d[0] * sign;
            const rank = Number(this.focusSquare[1]) + d[1] * sign;
            if (file < 0 || file > 7 || rank < 1 || rank > 8) return;
            const sq = FILES[file] + rank;
            this.buttons[this.focusSquare].tabIndex = -1;
            this.focusSquare = sq;
            this.buttons[sq].tabIndex = 0;
            this.buttons[sq].focus();
        }
    }

    window.Board = Board;
    window.ChessNames = { NAMES, pieceImage, pieceLabel };
})();
