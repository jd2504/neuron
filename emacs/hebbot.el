;;; hebbot.el --- Neuroscience study assistant  -*- lexical-binding: t; -*-

;; Author: JD
;; Version: 0.1.0
;; Package-Requires: ((emacs "28.1") (request "0.3.3"))
;; Keywords: education, neuroscience

;;; Commentary:

;; RAG-backed neuroscience study assistant with streaming chat.
;; Requires the Hebbot FastAPI backend running on localhost.
;;
;; Usage:
;;   M-x hebbot          Open the chat buffer
;;   M-x hebbot-ingest   Ingest a PDF into the knowledge base
;;
;; In the chat buffer:
;;   RET       Send input
;;   C-j       Insert newline
;;   C-c C-m   Switch study mode
;;   C-c C-s   Show session stats
;;   C-c C-c   Abort streaming response
;;   q         Quit (in conversation area) / self-insert (in input area)

;;; Code:

(require 'cl-lib)

;;; --- Customization ---

(defgroup hebbot nil
  "Neuroscience study assistant."
  :group 'applications
  :prefix "hebbot-")

(defcustom hebbot-server-url "http://localhost:8765"
  "URL of the Hebbot backend server."
  :type 'string
  :group 'hebbot)

(defcustom hebbot-default-mode "explain"
  "Default study mode for new sessions."
  :type '(choice (const "explain")
                 (const "quiz")
                 (const "deep_dive")
                 (const "misconception"))
  :group 'hebbot)

(defcustom hebbot-curl-executable "curl"
  "Path to the curl executable."
  :type 'string
  :group 'hebbot)

(defcustom hebbot-show-sources t
  "Whether to show source citations in a side window."
  :type 'boolean
  :group 'hebbot)

;;; --- Faces ---

(defface hebbot-user-face
  '((t :inherit font-lock-keyword-face :weight bold))
  "Face for user message headers."
  :group 'hebbot)

(defface hebbot-assistant-face
  '((t :inherit font-lock-function-name-face :weight bold))
  "Face for assistant message headers."
  :group 'hebbot)

(defface hebbot-separator-face
  '((t :inherit shadow))
  "Face for the buffer header and separators."
  :group 'hebbot)

(defface hebbot-source-book-face
  '((t :inherit font-lock-type-face :weight bold))
  "Face for book names in source citations."
  :group 'hebbot)

;;; --- Dependencies ---

(require 'hebbot-api)
(require 'hebbot-ui)

;;; --- Buffer-local variables ---

(defvar-local hebbot--session-id nil
  "Current session ID (UUID string, set after first server response).")

(defvar-local hebbot--current-mode nil
  "Current study mode string.")

(defvar-local hebbot--input-marker nil
  "Marker at the start of the \"> \" input prompt.")

(defvar-local hebbot--streaming-p nil
  "Non-nil while a streaming response is in progress.")

(defvar-local hebbot--curl-process nil
  "The curl process for the active SSE stream.")

(defvar-local hebbot--stream-insert-marker nil
  "Marker where streaming tokens are inserted (advances with each token).")

(defvar-local hebbot--thinking-timer nil
  "Timer driving the thinking animation.")

(defvar-local hebbot--thinking-overlay nil
  "Overlay displaying the action potential thinking animation.")

(defvar-local hebbot--thinking-frame-index 0
  "Current frame index in the thinking animation.")

;;; --- Keymap ---

(defvar hebbot-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "RET") #'hebbot-send-input)
    (define-key map (kbd "C-j") #'hebbot-newline)
    (define-key map (kbd "C-c C-m") #'hebbot-set-mode)
    (define-key map (kbd "C-c C-s") #'hebbot-show-stats)
    (define-key map (kbd "C-c C-c") #'hebbot-abort)
    (define-key map (kbd "q") #'hebbot-maybe-quit)
    map)
  "Keymap for `hebbot-mode'.")

;;; --- Major mode ---

(define-derived-mode hebbot-mode org-mode "Hebbot"
  "Major mode for the Hebbot neuroscience study assistant.

\\{hebbot-mode-map}"
  (setq hebbot--current-mode hebbot-default-mode)
  (visual-line-mode 1)
  (setq-local org-startup-indented nil)
  (setq-local org-startup-folded nil)
  (font-lock-add-keywords nil
    '(("^you: " 0 'hebbot-user-face t)
      ("^hebbot: " 0 'hebbot-assistant-face t))
    'append)
  (setq-local mode-line-format
              '(" " mode-name
                " [" (:eval hebbot--current-mode) "]"
                (:eval (if hebbot--streaming-p " ..." ""))
                " \u2014 "
                (:eval (if hebbot--session-id
                           (substring hebbot--session-id 0 8)
                         "new")))))

(defun hebbot-maybe-quit ()
  "Quit Hebbot if point is in the conversation area, otherwise self-insert."
  (interactive)
  (if (and hebbot--input-marker
           (>= (point) hebbot--input-marker))
      (call-interactively #'self-insert-command)
    (call-interactively #'hebbot-quit)))

;;; --- Entry points ---

;;;###autoload
(defun hebbot ()
  "Open the Hebbot neuroscience study assistant."
  (interactive)
  (let ((buf (get-buffer-create "*Hebbot*")))
    (with-current-buffer buf
      (unless (derived-mode-p 'hebbot-mode)
        (hebbot-mode)
        (hebbot-ui--init-buffer)))
    (pop-to-buffer-same-window buf)))

;;;###autoload
(defun hebbot-ingest (pdf-path)
  "Ingest a PDF at PDF-PATH into the knowledge base."
  (interactive "fPDF file: ")
  (message "Ingesting %s..." (file-name-nondirectory pdf-path))
  (hebbot-api--ingest
   (expand-file-name pdf-path)
   (lambda (data)
     (if data
         (message "Ingested: %d chunks from \"%s\""
                  (alist-get 'chunks_created data)
                  (alist-get 'book data))
       (message "Ingestion failed")))))

(provide 'hebbot)
;;; hebbot.el ends here
