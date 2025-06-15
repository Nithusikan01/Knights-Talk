const { ipcRenderer } = require('electron');

let whiteCapturedPieces = [];
let blackCapturedPieces = [];

function addMessageToPanel(message, isUserMessage = false) {
    const messagePanel = document.getElementById('messagePanel');
    const messageElement = document.createElement('div');

    // Check the last message in the panel
    const lastMessage = messagePanel.lastElementChild ? messagePanel.lastElementChild.textContent : '';

    // Determine the message type and apply styles accordingly
    if (lastMessage.includes('Move Please')) {
        messageElement.className = 'message light-green-message';
    } else {
        messageElement.className = isUserMessage ? 'message user-message' : 'message system-message';
    }

    messageElement.textContent = message;
    messagePanel.appendChild(messageElement);

    // Scroll to the bottom to show the latest message
    messagePanel.scrollTop = messagePanel.scrollHeight;
}

ipcRenderer.on('backend-message', (event, message) => {
    console.log(`Backend: ${message.message}`);
    addMessageToPanel(message.message); // System message

    if (message.message.includes("Starting the game")) {
        document.getElementById('placeholderImage').style.display = 'block';
        document.getElementById('loadingSign').style.display = 'block';
    }
});

ipcRenderer.on('board-update', (event, board) => {
    console.log(`Received board update:\n${board}`);
    document.querySelector('.container').style.display = 'flex';

    if (board && board.trim()) {
        document.getElementById('chessboard').style.display = 'grid';
        updateBoardFromText(board);

        // Apply the blur to the placeholder image
        const placeholderImage = document.getElementById('placeholderImage');
        placeholderImage.style.filter = 'blur(10px)';
        placeholderImage.style.transition = 'filter 1s ease-in-out';

        // Change the background image after the chessboard is loaded
        document.body.style.backgroundImage = "url('assets/logo_1.jpeg')";
        document.body.style.backgroundSize = "cover";
        document.body.style.backgroundPosition = "center";

        // Optionally hide the placeholder image after changing the background
        setTimeout(() => {
            placeholderImage.style.display = 'none';
        }, 1000); // Hide after the blur transition is complete

        // Optionally hide the loading sign after loading is complete
        document.getElementById('loadingSign').style.display = 'none';
    } else {
        console.error("Received an empty or invalid board state");
    }
});

function createSquare(pieceChar, isBlack, isInCheck) {
    const square = document.createElement('div');
    square.className = 'square ' + (isBlack ? 'black' : 'white');
    if (isInCheck) {
        square.style.backgroundColor = 'red';
    }
    if (pieceChar !== '.' && pieceChar) {
        const piece = document.createElement('span');
        piece.className = 'piece';
        piece.textContent = pieceChar;
        square.appendChild(piece);
    }
    return square;
}

function updateBoardFromText(boardText) {
    const board = document.createDocumentFragment();
    const rows = boardText.trim().split('\n');
    let isBlack = false;

    rows.forEach(row => {
        row.trim().split('').forEach(pieceChar => {
            const isInCheck = (pieceChar.toLowerCase() === 'k') && isKingInCheck();
            const square = createSquare(pieceChar, isBlack, isInCheck);
            board.appendChild(square);
            isBlack = !isBlack;
        });
        isBlack = !isBlack;
    });

    const chessboardElement = document.getElementById('chessboard');
    chessboardElement.innerHTML = '';
    chessboardElement.appendChild(board);
}

function isKingInCheck() {
    return false; // Implement actual logic here
}

document.getElementById('submitMoveButton').addEventListener('click', () => {
    const inputField = document.getElementById('moveInput');
    const moveInput = inputField.value.trim(); // Trim whitespace

    if (moveInput) {
        console.log(`Submitting move: ${moveInput}`);
        ipcRenderer.send('player-move', moveInput); // Send the move to the backend
        addMessageToPanel(`You: ${moveInput}`, 'player'); // Add the user's move to the panel as a player move

        inputField.value = ''; // Clear the input field after submission
    } else {
        console.log("No move entered"); // Optional: handle empty input case
        addMessageToPanel("No move entered. Please enter a move.", 'error'); // Inform user in the message panel if no move was entered
    }
});

