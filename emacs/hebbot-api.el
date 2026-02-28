;;; hebbot-api.el --- HTTP client for Hebbot  -*- lexical-binding: t; -*-

;; Copyright (C) 2026

;;; Commentary:

;; HTTP client layer for the Hebbot neuroscience study assistant.
;; Uses request.el for simple REST calls and curl subprocess for SSE streaming.

;;; Code:

(require 'request)
(require 'json)
(require 'cl-lib)

;; Forward declarations (defined in hebbot.el)
(defvar hebbot-server-url)
(defvar hebbot-curl-executable)

;;; --- Helpers ---

(defun hebbot-api--url (path)
  "Build full URL for PATH."
  (concat (string-trim-right hebbot-server-url "/") path))

;;; --- REST calls (via request.el) ---

(defun hebbot-api--health (callback)
  "Check server health, call CALLBACK with parsed response alist or nil."
  (request (hebbot-api--url "/health")
    :type "GET"
    :parser 'json-read
    :success (cl-function
              (lambda (&key data &allow-other-keys)
                (funcall callback data)))
    :error (cl-function
            (lambda (&key _error-thrown &allow-other-keys)
              (funcall callback nil)))))

(defun hebbot-api--get-session (session-id callback)
  "Fetch session SESSION-ID, call CALLBACK with parsed response or nil."
  (request (hebbot-api--url (format "/session/%s" session-id))
    :type "GET"
    :parser 'json-read
    :success (cl-function
              (lambda (&key data &allow-other-keys)
                (funcall callback data)))
    :error (cl-function
            (lambda (&key _error-thrown &allow-other-keys)
              (funcall callback nil)))))

(defun hebbot-api--delete-session (session-id callback)
  "Delete session SESSION-ID, call CALLBACK with parsed response or nil."
  (request (hebbot-api--url (format "/session/%s" session-id))
    :type "DELETE"
    :parser 'json-read
    :success (cl-function
              (lambda (&key data &allow-other-keys)
                (funcall callback data)))
    :error (cl-function
            (lambda (&key _error-thrown &allow-other-keys)
              (funcall callback nil)))))

(defun hebbot-api--ingest (pdf-path callback)
  "Ingest PDF at PDF-PATH, call CALLBACK with parsed response or nil."
  (request (hebbot-api--url "/ingest")
    :type "POST"
    :data (json-encode `((pdf_path . ,pdf-path)))
    :headers '(("Content-Type" . "application/json"))
    :parser 'json-read
    :success (cl-function
              (lambda (&key data &allow-other-keys)
                (funcall callback data)))
    :error (cl-function
            (lambda (&key _error-thrown &allow-other-keys)
              (funcall callback nil)))))

;;; --- SSE streaming (via curl subprocess) ---

(defun hebbot-api--chat-stream (message &optional session-id mode on-token on-done on-error)
  "Stream a chat request via SSE.
MESSAGE is the user query.  SESSION-ID and MODE are optional.
ON-TOKEN is called with each text chunk string.
ON-DONE is called with the parsed ChatResponse alist.
ON-ERROR is called with an error message string.
Returns the curl process."
  (let* ((body (json-encode
                `((message . ,message)
                  ,@(when session-id `((session_id . ,session-id)))
                  ,@(when mode `((mode . ,mode))))))
         (url (hebbot-api--url "/chat"))
         (process (make-process
                   :name "hebbot-sse"
                   :buffer nil
                   :command (list hebbot-curl-executable
                                 "-N" "-s" "-S"
                                 "-X" "POST"
                                 "-H" "Content-Type: application/json"
                                 "-d" "@-"
                                 url)
                   :connection-type 'pipe
                   :coding 'utf-8
                   :filter #'hebbot-api--sse-filter
                   :sentinel #'hebbot-api--sse-sentinel)))
    (process-put process 'hebbot-sse-buffer "")
    (process-put process 'hebbot-on-token (or on-token #'ignore))
    (process-put process 'hebbot-on-done (or on-done #'ignore))
    (process-put process 'hebbot-on-error (or on-error #'ignore))
    (process-send-string process body)
    (process-send-eof process)
    process))

(defun hebbot-api--sse-filter (process output)
  "Process filter for SSE stream.
Accumulates OUTPUT from PROCESS, splits on double newlines, dispatches events."
  (let ((buf (concat (process-get process 'hebbot-sse-buffer) output)))
    ;; Split on event boundaries (\n\n or \r\n\r\n)
    (while (string-match "\\(?:\r\n\r\n\\|\n\n\\)" buf)
      (let* ((boundary (match-end 0))
             (event-text (substring buf 0 (match-beginning 0)))
             (event-type nil)
             (event-data nil))
        (setq buf (substring buf boundary))
        ;; Parse event: and data: fields
        (dolist (line (split-string event-text "\\(?:\r\n\\|\n\\)"))
          (cond
           ((string-match "\\`event: *\\(.*\\)" line)
            (setq event-type (match-string 1 line)))
           ((string-match "\\`data: ?\\(.*\\)" line)
            (setq event-data
                  (if event-data
                      (concat event-data "\n" (match-string 1 line))
                    (match-string 1 line))))))
        ;; Dispatch based on event type
        (when event-data
          (pcase event-type
            ("token"
             (funcall (process-get process 'hebbot-on-token) event-data))
            ("done"
             (condition-case err
                 (let ((parsed (json-read-from-string event-data)))
                   (funcall (process-get process 'hebbot-on-done) parsed))
               (error
                (funcall (process-get process 'hebbot-on-error)
                         (format "Failed to parse done event: %s" err)))))
            ("error"
             (let ((msg (condition-case nil
                            (alist-get 'error (json-read-from-string event-data))
                          (error event-data))))
               (funcall (process-get process 'hebbot-on-error)
                        (or msg event-data))))))))
    (process-put process 'hebbot-sse-buffer buf)))

(defun hebbot-api--sse-sentinel (process _event)
  "Sentinel for SSE PROCESS.  Reports errors on abnormal exit."
  (when (eq (process-status process) 'exit)
    (let ((remaining (string-trim-right
                      (or (process-get process 'hebbot-sse-buffer) "")))
          (exit-code (process-exit-status process)))
      (cond
       ((not (zerop exit-code))
        (funcall (process-get process 'hebbot-on-error)
                 (if (string-empty-p remaining)
                     (format "Connection failed (curl exit %d)" exit-code)
                   (string-trim remaining))))
       ((not (string-empty-p remaining))
        (funcall (process-get process 'hebbot-on-error)
                 "Stream ended with incomplete data")))))
  (process-put process 'hebbot-sse-buffer nil))

(defun hebbot-api--abort-stream (process)
  "Kill the curl PROCESS if it is still running."
  (when (and process (process-live-p process))
    (delete-process process)))

(provide 'hebbot-api)
;;; hebbot-api.el ends here
