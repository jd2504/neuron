;;; hebbot-ui.el --- UI components for Hebbot  -*- lexical-binding: t; -*-

;; Copyright (C) 2026

;;; Commentary:

;; Buffer management, rendering, and interactive commands for the Hebbot
;; neuroscience study assistant.

;;; Code:

(require 'hebbot-api)
(require 'seq)

;; Forward declarations (defined in hebbot.el)
(defvar hebbot-server-url)
(defvar hebbot-show-sources)
(defvar hebbot-default-mode)
(defvar hebbot--session-id)
(defvar hebbot--current-mode)
(defvar hebbot--input-marker)
(defvar hebbot--streaming-p)
(defvar hebbot--curl-process)
(defvar hebbot--stream-insert-marker)
(defvar hebbot--thinking-timer)
(defvar hebbot--thinking-overlay)
(defvar hebbot--thinking-frame-index)

;;; --- Buffer initialization ---

(defun hebbot-ui--init-buffer ()
  "Initialize the *Hebbot* buffer with header, separator, and input prompt."
  (let ((inhibit-read-only t))
    (erase-buffer)
    ;; Header
    (insert (propertize "hebbot \u2014 what fires together stays on the exam...\n"
                        'face 'hebbot-separator-face
                        'read-only t
                        'rear-nonsticky '(read-only)))
    ;; Separator
    (insert (propertize (concat (make-string 50 ?\u2500) "\n")
                        'face 'hebbot-separator-face
                        'read-only t
                        'rear-nonsticky '(read-only)))
    ;; Record position, then insert prompt
    (let ((marker-pos (point)))
      (insert (propertize "> "
                          'read-only t
                          'rear-nonsticky '(read-only)))
      (setq hebbot--input-marker (copy-marker marker-pos))
      ;; insertion type nil: marker stays put when text is inserted at it
      (set-marker-insertion-type hebbot--input-marker nil))
    (goto-char (point-max))))

;;; --- Input handling ---

(defun hebbot-ui--get-input ()
  "Return the text in the input area (after the \"> \" prompt), or nil if empty."
  (let ((start (+ (marker-position hebbot--input-marker) 2)))
    (when (<= start (point-max))
      (let ((text (string-trim
                   (buffer-substring-no-properties start (point-max)))))
        (unless (string-empty-p text) text)))))

(defun hebbot-ui--clear-input ()
  "Clear the input area, leaving just the \"> \" prompt."
  (delete-region (+ (marker-position hebbot--input-marker) 2) (point-max))
  (goto-char (point-max)))

;;; --- Conversation rendering ---

(defun hebbot-ui--make-title (question)
  "Derive a short org heading title from QUESTION (first 6 words)."
  (let* ((clean (string-trim (replace-regexp-in-string "\\?+$" "" question)))
         (words (split-string clean "[ \t\n]+" t))
         (title (mapconcat #'identity (seq-take words 6) " ")))
    (if (> (length clean) (length title))
        (concat title "\u2026")
      title)))

(defun hebbot-ui--insert-user-message (title text)
  "Insert org heading TITLE and colored user TEXT above the input area."
  (let ((inhibit-read-only t))
    (save-excursion
      (goto-char hebbot--input-marker)
      (insert (propertize (concat "\n\n** " title "\n")
                          'read-only t
                          'rear-nonsticky '(read-only))
              (propertize "you: "
                          'face 'hebbot-user-face
                          'read-only t
                          'rear-nonsticky '(read-only))
              (propertize (concat text "\n\n")
                          'read-only t
                          'rear-nonsticky '(read-only)))
      (set-marker hebbot--input-marker (point)))))

(defun hebbot-ui--begin-assistant-message ()
  "Insert the colored Hebbot label and set up the stream insert marker."
  (let ((inhibit-read-only t))
    (save-excursion
      (goto-char hebbot--input-marker)
      (insert (propertize "hebbot: "
                          'face 'hebbot-assistant-face
                          'read-only t
                          'rear-nonsticky '(read-only)))
      (let ((stream-pos (point)))
        (insert (propertize "\n" 'read-only t 'rear-nonsticky '(read-only)))
        (set-marker hebbot--input-marker (point))
        (setq hebbot--stream-insert-marker (copy-marker stream-pos t))))))

;;; --- Thinking animation ---

(defconst hebbot-ui--thinking-frames
  (let ((width 10) frames)
    (dotimes (i (1- width))
      (push (concat (make-string i ?\u2500) "\u2571\u2572"
                    (make-string (- width 2 i) ?\u2500))
            frames))
    (nreverse frames))
  "Action potential animation frames (spike propagating rightward).")

(defun hebbot-ui--start-thinking ()
  "Start the action potential thinking animation at the stream insert marker."
  (hebbot-ui--stop-thinking)
  (when hebbot--stream-insert-marker
    (setq hebbot--thinking-overlay
          (make-overlay hebbot--stream-insert-marker hebbot--stream-insert-marker))
    (setq hebbot--thinking-frame-index 0)
    (overlay-put hebbot--thinking-overlay 'after-string
                 (propertize (nth 0 hebbot-ui--thinking-frames) 'face 'shadow))
    (let ((buf (current-buffer)))
      (setq hebbot--thinking-timer
            (run-at-time 0.12 0.12
                         (lambda ()
                           (when (buffer-live-p buf)
                             (with-current-buffer buf
                               (hebbot-ui--thinking-tick)))))))))

(defun hebbot-ui--thinking-tick ()
  "Advance the thinking animation by one frame."
  (when hebbot--thinking-overlay
    (setq hebbot--thinking-frame-index
          (mod (1+ hebbot--thinking-frame-index)
               (length hebbot-ui--thinking-frames)))
    (overlay-put hebbot--thinking-overlay 'after-string
                 (propertize (nth hebbot--thinking-frame-index
                                  hebbot-ui--thinking-frames)
                             'face 'shadow))))

(defun hebbot-ui--stop-thinking ()
  "Stop the thinking animation and remove the overlay."
  (when hebbot--thinking-timer
    (cancel-timer hebbot--thinking-timer)
    (setq hebbot--thinking-timer nil))
  (when hebbot--thinking-overlay
    (delete-overlay hebbot--thinking-overlay)
    (setq hebbot--thinking-overlay nil)))

(defun hebbot-ui--insert-token (token)
  "Insert streaming TOKEN at the stream insert marker."
  (when hebbot--stream-insert-marker
    (when hebbot--thinking-overlay
      (hebbot-ui--stop-thinking))
    (let ((inhibit-read-only t))
      (save-excursion
        (goto-char hebbot--stream-insert-marker)
        (insert token)))
    ;; Auto-scroll to follow streaming output
    (let ((win (get-buffer-window (current-buffer))))
      (when win
        (with-selected-window win
          (goto-char hebbot--stream-insert-marker)
          (recenter -3))))))

(defun hebbot-ui--handle-done (response)
  "Handle the done event with parsed RESPONSE alist.
Stores session-id, makes streamed text read-only, optionally shows sources."
  (let ((session-id (alist-get 'session_id response))
        (sources (alist-get 'sources response)))
    ;; Store session ID
    (when session-id
      (setq hebbot--session-id session-id))
    ;; Make entire conversation area read-only
    (let ((inhibit-read-only t))
      (put-text-property (point-min) (marker-position hebbot--input-marker)
                         'read-only t))
    ;; Reset streaming state
    (hebbot-ui--stop-thinking)
    (setq hebbot--streaming-p nil)
    (setq hebbot--curl-process nil)
    (setq hebbot--stream-insert-marker nil)
    (force-mode-line-update)
    ;; Move cursor to input area
    (goto-char (+ (marker-position hebbot--input-marker) 2))
    (let ((win (get-buffer-window (current-buffer))))
      (when win (set-window-point win (point))))
    ;; Show sources
    (when (and hebbot-show-sources sources (> (length sources) 0))
      (hebbot-ui--display-sources sources))))

(defun hebbot-ui--handle-error (error-msg)
  "Handle a streaming error.  Insert ERROR-MSG in the buffer and reset state."
  (let ((inhibit-read-only t))
    (save-excursion
      (goto-char (or hebbot--stream-insert-marker hebbot--input-marker))
      (insert (propertize (format "\n[Error: %s]\n" error-msg)
                          'face 'error
                          'read-only t
                          'rear-nonsticky '(read-only)))
      (when hebbot--input-marker
        (set-marker hebbot--input-marker (point)))))
  (hebbot-ui--stop-thinking)
  (setq hebbot--streaming-p nil)
  (setq hebbot--curl-process nil)
  (setq hebbot--stream-insert-marker nil)
  (force-mode-line-update))

;;; --- Sources display ---

(defun hebbot-ui--display-sources (sources)
  "Display SOURCES in the *Hebbot Sources* side window.
SOURCES is a vector of alists from the ChatResponse."
  (let ((buf (get-buffer-create "*Hebbot Sources*")))
    (with-current-buffer buf
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (propertize "Sources\n" 'face 'bold))
        (insert (make-string 40 ?\u2500) "\n\n")
        (seq-do
         (lambda (src)
           (let ((book (alist-get 'book src))
                 (chapter (alist-get 'chapter src))
                 (section (alist-get 'section src))
                 (page-start (alist-get 'page_start src))
                 (page-end (alist-get 'page_end src))
                 (score (alist-get 'score src)))
             (insert (propertize (capitalize (or book "?"))
                                 'face 'hebbot-source-book-face)
                     (format " \u2014 Ch.%s" (or chapter "?"))
                     (if section (format ": %s" section) "")
                     (format " (pp.%d\u2013%d)" (or page-start 0) (or page-end 0))
                     (format "  [%.2f]" (or score 0.0))
                     "\n")))
         sources))
      (goto-char (point-min))
      (special-mode))
    (display-buffer-in-side-window buf '((side . right) (window-width . 0.3)))))

;;; --- Interactive commands ---

(defun hebbot-send-input ()
  "Send the current input to the server and stream the response."
  (interactive)
  (when hebbot--streaming-p
    (user-error "Already streaming a response \u2014 wait or C-c C-c to abort"))
  (let ((input (hebbot-ui--get-input)))
    (unless input
      (user-error "Nothing to send"))
    ;; Insert user message and clear input area
    (hebbot-ui--insert-user-message (hebbot-ui--make-title input) input)
    (hebbot-ui--clear-input)
    ;; Set up assistant response area
    (hebbot-ui--begin-assistant-message)
    (hebbot-ui--start-thinking)
    (setq hebbot--streaming-p t)
    (force-mode-line-update)
    ;; Launch streaming request
    (let ((buf (current-buffer)))
      (setq hebbot--curl-process
            (hebbot-api--chat-stream
             input
             hebbot--session-id
             hebbot--current-mode
             ;; on-token
             (lambda (token)
               (when (buffer-live-p buf)
                 (with-current-buffer buf
                   (hebbot-ui--insert-token token))))
             ;; on-done
             (lambda (response)
               (when (buffer-live-p buf)
                 (with-current-buffer buf
                   (hebbot-ui--handle-done response))))
             ;; on-error
             (lambda (err)
               (when (buffer-live-p buf)
                 (with-current-buffer buf
                   (hebbot-ui--handle-error err)))))))))

(defun hebbot-newline ()
  "Insert a literal newline in the input area."
  (interactive)
  (insert "\n"))

(defun hebbot-set-mode (mode)
  "Set the study MODE for this session.
Modes: explain, quiz, deep_dive, misconception."
  (interactive
   (list (completing-read "Mode: " '("explain" "quiz" "deep_dive" "misconception")
                          nil t nil nil hebbot--current-mode)))
  (setq hebbot--current-mode mode)
  (force-mode-line-update)
  (message "Mode set to: %s" mode))

(defun hebbot-show-stats ()
  "Display session stats in the minibuffer."
  (interactive)
  (unless hebbot--session-id
    (user-error "No active session"))
  (hebbot-api--get-session
   hebbot--session-id
   (lambda (data)
     (if data
         (message "Session: %d messages | topics: %s | quiz: %d/%d"
                  (alist-get 'message_count data 0)
                  (let ((topics (append (alist-get 'topics_covered data) nil)))
                    (if topics
                        (mapconcat #'identity topics ", ")
                      "none"))
                  (alist-get 'correct (alist-get 'quiz_score data) 0)
                  (alist-get 'total (alist-get 'quiz_score data) 0))
       (message "Failed to fetch session stats")))))

(defun hebbot-abort ()
  "Abort the current streaming response."
  (interactive)
  (when hebbot--curl-process
    (hebbot-ui--stop-thinking)
    (hebbot-api--abort-stream hebbot--curl-process)
    (let ((inhibit-read-only t))
      (save-excursion
        (goto-char (or hebbot--stream-insert-marker hebbot--input-marker))
        (insert (propertize " [aborted]" 'face 'warning))))
    (setq hebbot--streaming-p nil)
    (setq hebbot--curl-process nil)
    (setq hebbot--stream-insert-marker nil)
    (force-mode-line-update)
    (message "Stream aborted")))

(defun hebbot-quit (&optional delete-session)
  "Quit Hebbot.  With prefix arg DELETE-SESSION, delete the server session."
  (interactive "P")
  (when hebbot--streaming-p
    (hebbot-abort))
  (when (and delete-session hebbot--session-id)
    (hebbot-api--delete-session
     hebbot--session-id
     (lambda (_) (message "Session deleted"))))
  (quit-window))

(provide 'hebbot-ui)
;;; hebbot-ui.el ends here
