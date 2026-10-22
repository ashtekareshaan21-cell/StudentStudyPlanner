// static/timer.js
// Timer Configuration and functions for study sessions

document.addEventListener('DOMContentLoaded', () => {
    const timerTimeEl = document.getElementById('timerTime');
    if (!timerTimeEl) return;

    // Load study hours from data attribute
    const studyHours = parseFloat(timerTimeEl.getAttribute('data-study-hours') || 0);
    const totalSeconds = studyHours * 3600;  // Convert hours to seconds
    let remainingSeconds = totalSeconds;
    let timerInterval = null;
    let isRunning = false;
    let isPaused = false;

    // Elements
    const startBtn = document.getElementById('startBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const resumeBtn = document.getElementById('resumeBtn');
    const resetBtn = document.getElementById('resetBtn');
    const timerProgress = document.getElementById('timerProgress');
    const timerStatus = document.getElementById('timerStatus');

    function formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    function updateDisplay() {
        timerTimeEl.textContent = formatTime(remainingSeconds);
        
        // Update progress circle
        const circumference = 2 * Math.PI * 90;
        const progress = (remainingSeconds / totalSeconds) * circumference;
        timerProgress.style.strokeDashoffset = progress;

        // Update status message
        if (remainingSeconds <= 0) {
            timerStatus.textContent = '🎉 Study session completed! Great job!';
            timerStatus.style.color = 'var(--success-color)';
            clearInterval(timerInterval);
            isRunning = false;
            updateButtons();
            playCompletionSound();
        } else if (remainingSeconds <= 300) {
            timerStatus.textContent = `⏰ Only ${Math.ceil(remainingSeconds / 60)} minutes left!`;
            timerStatus.style.color = 'var(--danger-color)';
        } else {
            timerStatus.textContent = `⏳ Study in progress...`;
            timerStatus.style.color = 'var(--primary-color)';
        }
    }

    function startTimer() {
        if (!isRunning) {
            isRunning = true;
            isPaused = false;
            updateButtons();
            
            timerInterval = setInterval(() => {
                if (remainingSeconds > 0) {
                    remainingSeconds--;
                    updateDisplay();
                } else {
                    clearInterval(timerInterval);
                    isRunning = false;
                    updateButtons();
                }
            }, 1000);
        }
    }

    function pauseTimer() {
        if (isRunning) {
            clearInterval(timerInterval);
            isRunning = false;
            isPaused = true;
            updateButtons();
            timerStatus.textContent = '⏸ Timer paused';
            timerStatus.style.color = 'var(--warning-color)';
        }
    }

    function resumeTimer() {
        if (isPaused) {
            startTimer();
            isPaused = false;
        }
    }

    function resetTimer() {
        clearInterval(timerInterval);
        remainingSeconds = totalSeconds;
        isRunning = false;
        isPaused = false;
        updateDisplay();
        updateButtons();
        timerStatus.textContent = 'Ready to start your study session';
        timerStatus.style.color = 'var(--dark-color)';
    }

    function updateButtons() {
        if (isRunning) {
            startBtn.style.display = 'none';
            pauseBtn.style.display = 'inline-block';
            resumeBtn.style.display = 'none';
        } else if (isPaused) {
            startBtn.style.display = 'none';
            pauseBtn.style.display = 'none';
            resumeBtn.style.display = 'inline-block';
        } else {
            startBtn.style.display = 'inline-block';
            pauseBtn.style.display = 'none';
            resumeBtn.style.display = 'none';
        }
    }

    function playCompletionSound() {
        // Create a simple beep sound
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            
            oscillator.connect(gain);
            gain.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            
            gain.gain.setValueAtTime(0.3, audioContext.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.5);
        } catch (e) {
            console.log("AudioContext blocked or not supported:", e);
        }
    }

    // Attach event listeners
    startBtn.addEventListener('click', startTimer);
    pauseBtn.addEventListener('click', pauseTimer);
    resumeBtn.addEventListener('click', resumeTimer);
    resetBtn.addEventListener('click', resetTimer);

    // Initial display update
    updateDisplay();
});
