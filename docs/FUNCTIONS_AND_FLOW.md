# CedarPy Functions and Execution Flow (Auto-generated Index + Timeline)

This document contains:
- A complete index of every function and method in this repository (project code only), grouped by file
- A duplicate-name report to highlight potential duplication risks
- A precise execution timeline of what runs when a user submits a prompt via WebSocket chat, with code references

Generated: latest at document creation time. If code changes significantly, regenerate this file.

Notes
- Scope: Project code under this repo. Excludes vendor/site-packages, build artifacts, and packaging/build-embedded.
- Excluded directories: .git, __pycache__, .venv, venv, env, node_modules, dist, build, packaging/build-embedded, lib

---

## Function Index (Project only)

- Root: /Users/leonardspeiser/Projects/cedarpy
- Excluded: .git, .venv, __pycache__, build, dist, env, lib, node_modules, packaging/build-embedded, venv
- Total functions/methods found: 623

## Inventory by file
### agents/__init__.py
- L18: [method] PlanAgent.__init__
- L21: [method] PlanAgent.execute
- L29: [method] WebAgent.__init__
- L32: [method] WebAgent.execute
- L40: [method] FileAgent.__init__
- L43: [method] FileAgent.execute
- L51: [method] DbAgent.__init__
- L54: [method] DbAgent.execute
- L62: [method] NotesAgent.__init__
- L65: [method] NotesAgent.execute
- L73: [method] ImagesAgent.__init__
- L76: [method] ImagesAgent.execute
- L84: [method] QuestionAgent.__init__
- L87: [method] QuestionAgent.execute
- L131: [function] get_agent

### agents/base_agent.py
- L40: [method] BaseAgent.__init__
- L45: [method] BaseAgent.execute
- L49: [method] BaseAgent.validate_context
- L56: [method] BaseAgent.create_success_result
- L66: [method] BaseAgent.create_error_result

### agents/code.py
- L23: [method] CodeAgent.__init__
- L26: [method] CodeAgent.execute
- L68: [method] CodeAgent._generate_code
- L101: [method] CodeAgent._is_safe_to_execute
- L125: [method] CodeAgent._execute_code

### agents/final.py
- L14: [method] FinalAgent.__init__
- L17: [method] FinalAgent.execute
- L52: [method] FinalAgent._is_simple_arithmetic
- L59: [method] FinalAgent._calculate_arithmetic
- L70: [method] FinalAgent._synthesize_results
- L92: [method] FinalAgent._generate_llm_answer

### cedar_app/api_routes.py
- L20: [function] settings_page
- L64: [function] settings_save
- L86: [function] api_model_change
- L119: [function] api_chat_ack
- L148: [function] serve_project_upload

### cedar_app/changelog_utils.py
- L16: [function] record_changelog
- L66: [function] add_version

### cedar_app/config.py
- L11: [function] _load_dotenv_files
- L17: [nested_function] _load_dotenv_files._parse_line
- L48: [function] _parse_env_file
- L67: [function] _initialize_environment
- L182: [function] initialize_directories

### cedar_app/database.py
- L51: [function] _project_dirs
- L60: [function] _ensure_project_storage
- L68: [function] _get_project_engine
- L85: [function] get_registry_db
- L94: [function] get_project_db
- L105: [function] save_thread_snapshot
- L165: [function] _migrate_project_files_ai_columns
- L194: [function] _migrate_thread_messages_columns
- L212: [function] _migrate_project_langextract_tables
- L224: [function] _migrate_project_notes_table
- L242: [function] _migrate_registry_metadata_json
- L296: [function] ensure_project_initialized

### cedar_app/db_utils.py
- L44: [function] _project_dirs
- L52: [function] _ensure_project_storage
- L59: [function] _get_project_engine
- L74: [function] get_registry_db
- L82: [function] get_project_db
- L96: [function] _migrate_project_files_ai_columns
- L124: [function] _migrate_thread_messages_columns
- L141: [function] _migrate_project_langextract_tables
- L157: [function] save_thread_snapshot
- L220: [function] ensure_project_initialized

### cedar_app/file_upload_handler.py
- L16: [function] register_file_upload_routes
- L20: [nested_function] register_file_upload_routes.process_uploaded_file
- L59: [nested_function] register_file_upload_routes.websocket_file_processor

### cedar_app/file_utils.py
- L25: [function] is_probably_text
- L49: [function] interpret_file

### cedar_app/llm/client.py
- L9: [function] _llm_client_config
- L36: [nested_function] _llm_client_config.__init__
- L39: [nested_function] _llm_client_config.__init__
- L42: [nested_function] _llm_client_config.__init__
- L45: [nested_function] _llm_client_config.create
- L132: [nested_function] _llm_client_config.__init__
- L135: [nested_function] _llm_client_config.__init__
- L156: [function] _llm_classify_file
- L248: [nested_function] _llm_classify_file._clip

### cedar_app/llm/tabular_import.py
- L8: [function] tabular_import_via_llm

### cedar_app/llm_utils.py
- L32: [function] llm_client_config
- L59: [nested_function] llm_client_config.__init__
- L62: [nested_function] llm_client_config.__init__
- L65: [nested_function] llm_client_config.__init__
- L68: [nested_function] llm_client_config.create
- L154: [nested_function] llm_client_config.__init__
- L157: [nested_function] llm_client_config.__init__
- L178: [function] _env_get
- L203: [function] llm_classify_file
- L260: [nested_function] llm_classify_file._clip
- L284: [function] llm_summarize_action
- L334: [function] llm_dataset_friendly_name
- L387: [function] snake_case
- L398: [function] suggest_table_name
- L403: [function] extract_code_from_markdown
- L416: [function] tabular_import_via_llm
- L516: [nested_function] tabular_import_via_llm.__getitem__
- L542: [nested_function] tabular_import_via_llm._safe_import
- L547: [nested_function] tabular_import_via_llm._safe_open

### cedar_app/routes/agents_route.py
- L10: [function] register_agents_route
- L14: [nested_function] register_agents_route.view_agents

### cedar_app/routes/chat_api.py
- L10: [function] register_chat_api_routes
- L14: [nested_function] register_chat_api_routes.create_new_chat
- L36: [nested_function] register_chat_api_routes.load_chat
- L60: [nested_function] register_chat_api_routes.update_chat
- L79: [nested_function] register_chat_api_routes.list_chats
- L87: [nested_function] register_chat_api_routes.get_active_chat

### cedar_app/routes/file_routes.py
- L12: [function] upload_file
- L27: [function] download_file

### cedar_app/routes/log_routes.py
- L15: [function] view_logs
- L34: [function] client_log

### cedar_app/routes/main_routes.py
- L15: [function] home
- L20: [function] projects_list
- L28: [function] about

### cedar_app/routes/project_routes.py
- L15: [function] view_project
- L32: [function] create_branch

### cedar_app/routes/project_thread_routes.py
- L21: [function] create_project
- L105: [function] create_thread

### cedar_app/routes/shell_routes.py
- L15: [function] _is_local_request
- L19: [function] require_shell_auth
- L35: [function] shell_ui

### cedar_app/routes/sql_routes.py
- L26: [function] make_table_branch_aware_impl
- L81: [function] undo_last_sql_impl
- L156: [function] execute_sql_impl

### cedar_app/routes/thread_routes.py
- L14: [function] list_threads
- L20: [function] get_thread_session

### cedar_app/routes/websocket_routes.py
- L11: [function] websocket_chat
- L23: [function] websocket_health

### cedar_app/scripts/extract_sql_routes.py
- L20: [function] extract_sql_routes

### cedar_app/shell_utils.py
- L30: [method] ShellJob.__init__
- L53: [method] ShellJob.append_line
- L68: [method] ShellJob.kill
- L82: [function] run_shell_job
- L85: [nested_function] run_shell_job._is_executable
- L91: [nested_function] run_shell_job._candidate_shells
- L106: [nested_function] run_shell_job._args_for
- L207: [method] ShellJobManager.__init__
- L213: [method] ShellJobManager.start_job
- L225: [method] ShellJobManager.get_job
- L240: [function] is_local_request
- L246: [function] require_shell_enabled_and_auth
- L273: [function] handle_shell_websocket
- L380: [function] handle_health_websocket

### cedar_app/tools/shell.py
- L23: [method] ShellJob.__init__
- L40: [method] ShellJob.append_line
- L53: [method] ShellJob.kill
- L70: [function] _run_job
- L71: [nested_function] _run_job._is_executable
- L77: [nested_function] _run_job._candidate_shells
- L92: [nested_function] _run_job._args_for
- L189: [function] start_shell_job
- L198: [function] get_shell_job

### cedar_app/ui_utils.py
- L28: [function] env_get
- L55: [function] env_set_many
- L105: [function] llm_reachability
- L176: [function] llm_reach_ok
- L185: [function] llm_reach_reason
- L194: [function] is_trivial_math
- L207: [function] get_client_log_js
- L286: [function] layout

### cedar_app/utils/ask_orchestrator.py
- L31: [function] ask_orchestrator
- L87: [nested_function] ask_orchestrator._files_index
- L107: [nested_function] ask_orchestrator._recent_changelog
- L123: [nested_function] ask_orchestrator._recent_assistant_msgs
- L188: [nested_function] ask_orchestrator._call_llm
- L204: [nested_function] ask_orchestrator._exec_sql
- L217: [nested_function] ask_orchestrator._exec_grep
- L243: [nested_function] ask_orchestrator._exec_code
- L246: [nested_function] ask_orchestrator.query
- L249: [nested_function] ask_orchestrator.list_files
- L252: [nested_function] ask_orchestrator.read
- L262: [nested_function] ask_orchestrator.open_path
- L271: [nested_function] ask_orchestrator.note
- L300: [nested_function] ask_orchestrator._exec_web
- L311: [nested_function] ask_orchestrator._exec_img
- L329: [nested_function] ask_orchestrator._exec_notes

### cedar_app/utils/branch_management.py
- L19: [function] create_branch
- L82: [function] delete_branch
- L165: [function] list_branches
- L209: [function] get_branch_info
- L263: [function] switch_branch
- L293: [function] rename_branch
- L357: [function] compare_branches

### cedar_app/utils/chat_persistence.py
- L20: [method] ChatManager.__init__
- L27: [method] ChatManager.get_next_chat_number
- L46: [method] ChatManager.get_chat_file_path
- L50: [method] ChatManager.create_chat
- L83: [method] ChatManager.get_chat
- L94: [method] ChatManager.update_chat
- L126: [method] ChatManager.add_message
- L138: [method] ChatManager.list_chats
- L167: [method] ChatManager.get_active_chat
- L176: [method] ChatManager.set_chat_status
- L180: [method] ChatManager.cleanup_old_chats
- L195: [method] ChatManager.delete_project_chats
- L222: [function] get_chat_manager

### cedar_app/utils/client_logging.py
- L32: [function] api_client_log
- L83: [function] api_client_logs_batch
- L128: [function] api_client_logs_query
- L174: [function] api_client_error_report
- L218: [function] cleanup_old_logs

### cedar_app/utils/code_collection.py
- L13: [function] collect_code_items

### cedar_app/utils/dataset_management.py
- L18: [function] create_dataset
- L92: [function] update_dataset
- L167: [function] delete_dataset
- L203: [function] get_dataset
- L226: [function] list_datasets
- L258: [function] search_datasets
- L295: [function] clone_dataset

### cedar_app/utils/dev_tools.py
- L26: [function] api_test_tool_exec

### cedar_app/utils/file_management.py
- L23: [function] file_extension_to_type
- L48: [function] interpret_file
- L131: [function] upload_file
- L302: [function] delete_file
- L344: [function] download_file
- L376: [function] list_files
- L413: [function] get_file_info

### cedar_app/utils/file_operations.py
- L32: [function] _run_langextract_ingest_background
- L97: [nested_function] _run_langextract_ingest_background._tabular_import_via_llm
- L138: [function] _run_upload_postprocess_background
- L294: [function] upload_file

### cedar_app/utils/file_upload.py
- L27: [function] serve_project_upload
- L61: [function] upload_file
- L217: [function] _run_upload_postprocess_background

### cedar_app/utils/file_utils.py
- L10: [function] interpret_file
- L25: [function] _is_probably_text

### cedar_app/utils/html.py
- L15: [function] escape
- L19: [function] layout
- L212: [function] projects_list_html

### cedar_app/utils/logging.py
- L25: [method] CedarBufferHandler.emit
- L53: [function] _install_unified_logging
- L69: [nested_function] _install_unified_logging._cedar_print
- L103: [nested_function] _install_unified_logging._cedar_logging_mw

### cedar_app/utils/note_management.py
- L19: [function] api_notes_save
- L92: [function] api_notes_list
- L125: [function] api_notes_get
- L157: [function] api_notes_delete
- L200: [function] api_notes_search

### cedar_app/utils/page_rendering.py
- L12: [function] projects_list_html
- L85: [function] project_page_html
- L263: [nested_function] project_page_html._file_label
- L288: [nested_function] project_page_html._code_label
- L323: [nested_function] project_page_html._file_detail_panel

### cedar_app/utils/project_management.py
- L29: [function] _hash_payload
- L38: [function] merge_to_main
- L224: [function] delete_all_files
- L261: [function] delete_project

### cedar_app/utils/sql_utils.py
- L25: [function] _dialect
- L30: [function] _safe_identifier
- L34: [function] _sql_quote
- L43: [function] _table_has_branch_columns
- L61: [function] _get_pk_columns
- L77: [function] _extract_where_clause
- L86: [function] _preprocess_sql_branch_aware
- L98: [function] _execute_sql
- L136: [function] _execute_sql_with_undo
- L318: [function] _render_sql_result_html
- L362: [function] handle_sql_websocket

### cedar_app/utils/sql_websocket.py
- L20: [function] ws_sqlx
- L62: [nested_function] ws_sqlx._resolve_branch_id

### cedar_app/utils/test_tools.py
- L27: [function] api_test_tool_exec
- L61: [function] _exec_sql_tool
- L101: [function] _exec_grep_tool
- L160: [function] _exec_code_tool
- L173: [nested_function] _exec_code_tool.query
- L188: [nested_function] _exec_code_tool.list_files
- L206: [nested_function] _exec_code_tool.read
- L270: [function] _exec_notes_tool
- L303: [function] _exec_img_tool

### cedar_app/utils/thread_chat.py
- L25: [function] thread_chat

### cedar_app/utils/thread_management.py
- L19: [function] api_threads_list
- L58: [function] api_threads_session
- L105: [function] api_chat_cancel_summary

### cedar_app/utils/ui_views.py
- L24: [function] view_logs
- L66: [function] view_changelog
- L152: [function] render_project_view

### cedar_app/utils/websocket_chat.py
- L29: [function] _ws_send_safe
- L51: [function] _register_ack
- L55: [function] _publish_relay_event

### cedar_langextract.py
- L31: [function] ensure_langextract_schema
- L67: [nested_function] ensure_langextract_schema._trigger_exists
- L109: [function] file_to_text
- L195: [function] chunk_document_insert
- L236: [function] retrieve_top_chunks

### cedar_orchestrator/advanced_orchestrator.py
- L73: [method] ShellAgent.__init__
- L77: [method] ShellAgent.process
- L359: [method] ShellAgent._format_history
- L371: [method] ShellAgent._basic_analysis
- L400: [method] CodeAgent.__init__
- L403: [method] CodeAgent.process
- L613: [method] ReasoningAgent.__init__
- L616: [method] ReasoningAgent.process
- L712: [method] SQLAgent.__init__
- L715: [method] SQLAgent.process
- L866: [method] GeneralAgent.__init__
- L869: [method] GeneralAgent.process
- L965: [method] MathAgent.__init__
- L968: [method] MathAgent.process
- L1053: [method] ResearchAgent.__init__
- L1056: [method] ResearchAgent.process
- L1147: [method] StrategyAgent.__init__
- L1150: [method] StrategyAgent.process
- L1240: [method] DataAgent.__init__
- L1244: [method] DataAgent.process
- L1358: [method] FileAgent.__init__
- L1364: [method] FileAgent.process
- L1587: [method] NotesAgent.__init__
- L1591: [method] NotesAgent.process
- L1687: [method] ChiefAgent.__init__
- L1690: [method] ChiefAgent.review_and_decide
- L2115: [method] ThinkerOrchestrator.__init__
- L2142: [method] ThinkerOrchestrator.process_file
- L2154: [method] ThinkerOrchestrator.think
- L2259: [method] ThinkerOrchestrator.orchestrate

### cedar_orchestrator/chief_agent_notes.py
- L18: [method] ChiefAgentNoteTaker.__init__
- L23: [method] ChiefAgentNoteTaker.save_agent_notes
- L74: [method] ChiefAgentNoteTaker._build_comprehensive_notes
- L124: [method] ChiefAgentNoteTaker._extract_key_finding
- L146: [method] ChiefAgentNoteTaker._generate_tags
- L181: [method] ChiefAgentNoteTaker.get_existing_notes
- L202: [method] EnhancedChiefAgentOrchestration.process_with_notes

### cedar_orchestrator/file_processing_agents.py
- L64: [method] FileReaderAgent.__init__
- L67: [method] FileReaderAgent.process
- L155: [method] PDFExtractionAgent.__init__
- L158: [method] PDFExtractionAgent.process
- L248: [method] OCRAgent.__init__
- L252: [method] OCRAgent.process
- L326: [method] LangExtractAgent.__init__
- L329: [method] LangExtractAgent.process
- L381: [method] ImageAnalysisAgent.__init__
- L384: [method] ImageAnalysisAgent.process
- L478: [method] SQLMetadataAgent.__init__
- L484: [method] SQLMetadataAgent._init_db
- L529: [method] SQLMetadataAgent.process
- L630: [method] FileProcessingOrchestrator.__init__
- L639: [method] FileProcessingOrchestrator.process_file

### cedar_orchestrator/ws_chat.py
- L24: [method] WSDeps.__init__
- L28: [function] register_ws_chat
- L53: [nested_function] register_ws_chat.ws_chat_with_project
- L60: [nested_function] register_ws_chat.ws_chat_simple
- L69: [function] handle_ws_chat
- L163: [nested_function] handle_ws_chat.__init__
- L170: [nested_function] handle_ws_chat.send_json

### cedar_tools/code.py
- L12: [function] tool_code
- L16: [nested_function] tool_code._cedar_query
- L21: [nested_function] tool_code._cedar_list_files
- L30: [nested_function] tool_code._cedar_read

### cedar_tools/compose.py
- L7: [function] tool_compose

### cedar_tools/db.py
- L3: [function] tool_db

### cedar_tools/download.py
- L10: [function] tool_download

### cedar_tools/extract.py
- L9: [function] tool_extract

### cedar_tools/image.py
- L7: [function] tool_image

### cedar_tools/notes.py
- L7: [function] tool_notes

### cedar_tools/shell.py
- L5: [function] tool_shell

### cedar_tools/tabular_import.py
- L8: [function] tool_tabular_import

### cedar_tools/web.py
- L9: [function] tool_web

### cedar_utils/ports.py
- L12: [function] choose_listen_port
- L47: [function] is_port_available

### cedarqt.py
- L65: [function] _init_logging
- L167: [function] _pid_is_running
- L177: [function] _acquire_single_instance_lock
- L215: [nested_function] _acquire_single_instance_lock._try_create
- L285: [method] RequestLogger.interceptRequest
- L295: [method] LoggingWebPage.__init__
- L300: [method] LoggingWebPage._append_console_log
- L309: [method] LoggingWebPage.javaScriptConsoleMessage
- L333: [method] LoggingWebPage.chooseFiles
- L347: [method] LoggingWebPage.createWindow
- L371: [function] _wait_for_server
- L387: [function] _find_pids_listening_on
- L418: [function] _http_get
- L428: [function] _preflight_cleanup_existing_server
- L470: [function] _launch_server_inprocess
- L474: [nested_function] _launch_server_inprocess._load_app_by_name
- L482: [nested_function] _launch_server_inprocess._load_app_from_candidates
- L522: [nested_function] _launch_server_inprocess._b2s
- L528: [nested_function] _launch_server_inprocess.__init__
- L530: [nested_function] _launch_server_inprocess.__call__
- L542: [nested_function] _launch_server_inprocess._send
- L575: [function] _open_full_disk_access_settings
- L591: [function] _maybe_prompt_full_disk_access_once
- L653: [function] main
- L699: [nested_function] main._show_text_dialog
- L724: [nested_function] main._copy_all
- L746: [nested_function] main._show_console_logs
- L754: [nested_function] main._show_page_source
- L756: [nested_function] main._got_html
- L803: [nested_function] main._graceful_shutdown
- L841: [nested_function] main.run_harness
- L843: [nested_function] main.js
- L859: [nested_function] main.wait_project_and_upload
- L867: [nested_function] main.click_submit
- L870: [nested_function] main.wait_uploaded
- L899: [nested_function] main._shutdown
- L929: [nested_function] main._sig_handler

### main.py
- L233: [function] _tabular_import_via_llm
- L246: [function] get_db
- L267: [function] record_changelog
- L275: [function] add_version
- L284: [function] start_shell_job
- L288: [function] get_shell_job
- L292: [function] require_shell_enabled_and_auth
- L321: [method] CedarBufferHandler.emit
- L348: [function] _install_unified_logging
- L364: [nested_function] _install_unified_logging._cedar_print
- L410: [function] catch_exceptions_middleware
- L423: [function] _cedar_logging_mw
- L517: [function] api_chat_ack
- L521: [function] _cedarpy_startup_llm_probe
- L536: [function] home
- L543: [function] settings_page
- L556: [function] settings_save
- L564: [function] api_model_change
- L592: [function] serve_project_upload
- L945: [function] api_shell_run
- L984: [function] ws_shell
- L996: [function] ws_health
- L1005: [function] ws_sql
- L1026: [function] api_client_log
- L1063: [function] api_chat_cancel_summary
- L1068: [function] api_test_tool_exec
- L1075: [function] merge_to_main
- L1082: [function] delete_all_files
- L1089: [function] make_table_branch_aware
- L1093: [function] delete_project
- L1101: [function] undo_last_sql
- L1104: [function] execute_sql
- L1178: [function] api_threads_list
- L1183: [function] api_threads_session
- L1188: [function] view_logs
- L1256: [function] merge_index_html
- L1278: [function] merge_index
- L1312: [function] merge_project_view
- L1380: [function] get_or_create_project_registry
- L1424: [function] create_project
- L1506: [function] view_project
- L1641: [function] create_branch
- L1669: [function] create_thread
- L1739: [function] ask_endpoint
- L1746: [function] thread_chat_endpoint
- L1754: [function] _ws_send_safe
- L1791: [function] upload_file

### main_helpers.py
- L14: [function] _get_redis
- L25: [function] _publish_relay_event
- L44: [function] _register_ack
- L53: [nested_function] _register_ack._timeout
- L78: [function] escape
- L82: [function] add_version
- L92: [function] ensure_main_branch
- L103: [function] file_extension_to_type
- L130: [function] branch_filter_ids
- L148: [function] current_branch

### migrations/add_note_fields.py
- L16: [function] get_project_databases
- L35: [function] table_exists
- L43: [function] column_exists
- L49: [function] add_column_if_missing
- L60: [function] migrate_notes_table
- L110: [function] migrate_registry_database
- L146: [function] main

### migrations/add_notes_dataset.py
- L17: [function] get_project_databases
- L36: [function] table_exists
- L44: [function] add_notes_dataset
- L137: [function] main

### run_cedarpy.py
- L17: [function] _init_logging
- L30: [function] _mask_dsn
- L112: [function] _kill_other_instances
- L165: [function] _doctor_log_paths
- L182: [function] _doctor_write
- L198: [function] run_doctor
- L304: [function] main
- L338: [nested_function] main.open_browser

### scripts/run_llm_tool_audit.py
- L57: [function] _print_header
- L63: [function] _print_block
- L72: [function] _env_bool
- L82: [function] _load_env_files
- L86: [nested_function] _load_env_files._parse_line
- L112: [function] _ensure_env
- L145: [method] App.__init__
- L152: [method] App.create_project
- L166: [method] App._tool_call
- L189: [method] App.sql_scalar
- L199: [function] main

### scripts/shell_headless.py
- L16: [function] run_headless
- L38: [function] main

### scripts/ws_backend_test.py
- L32: [function] parse_args
- L43: [function] run
- L96: [function] main

### test_agent_selection.py
- L12: [function] test_agent_selection

### test_chat_functionality.py
- L12: [function] test_chat

### test_complete_chat.py
- L37: [function] test_single_query
- L128: [function] run_all_tests

### test_extracted_content.py
- L12: [function] test_extracted_content_api

### test_file_agent.py
- L17: [function] test_file_agent

### test_new_flow.py
- L21: [function] test_simple_arithmetic
- L116: [function] test_code_generation
- L149: [function] main

### test_new_formatting.py
- L11: [function] test_orchestrator

### test_notes_functionality.py
- L16: [function] test_notes_database
- L198: [function] test_chief_agent_notes
- L230: [function] check_ui_rendering

### test_notes_saving.py
- L14: [function] check_notes_before
- L30: [function] check_notes_after
- L55: [function] simulate_agent_results

### test_orchestrator.py
- L17: [method] MockWebSocket.__init__
- L20: [method] MockWebSocket.send_json
- L26: [function] test_simple_query

### test_project_creation.py
- L13: [function] test_project_creation
- L64: [function] main

### test_refactored_app.py
- L14: [function] test_endpoint
- L40: [function] main

### test_shell_agent.py
- L13: [function] test_shell_agent

### test_upload.py
- L15: [function] test_upload

### tests/conftest.py
- L7: [function] _isolate_db
- L22: [function] _parse_dotenv
- L44: [function] pytest_sessionstart

### tests/quick_test.py
- L12: [function] test_basic_connectivity
- L82: [nested_function] test_basic_connectivity.test_ws
- L127: [nested_function] test_basic_connectivity.test_math

### tests/run_all_tests.py
- L26: [method] CedarPyTestRunner.__init__
- L36: [method] CedarPyTestRunner.check_app_running
- L45: [method] CedarPyTestRunner.start_app_if_needed
- L83: [method] CedarPyTestRunner.run_core_tests
- L96: [method] CedarPyTestRunner.run_project_tests
- L109: [method] CedarPyTestRunner.run_websocket_tests
- L121: [method] CedarPyTestRunner.generate_summary
- L145: [method] CedarPyTestRunner.save_report
- L160: [method] CedarPyTestRunner.print_final_summary
- L193: [method] CedarPyTestRunner.cleanup
- L206: [method] CedarPyTestRunner.run_all
- L256: [function] main

### tests/test_cedar_tools.py
- L13: [function] test_tool_shell_echo_hello
- L19: [function] test_tool_db_stub_execute_sql
- L21: [nested_function] test_tool_db_stub_execute_sql._exec
- L31: [function] test_tool_web_fetch_example_org

### tests/test_config.py
- L48: [function] get_headers

### tests/test_core_functionality.py
- L14: [method] CoreFunctionalityTests.__init__
- L21: [method] CoreFunctionalityTests.test_server_running
- L34: [method] CoreFunctionalityTests.test_home_page_loads
- L53: [method] CoreFunctionalityTests.test_api_health_check
- L72: [method] CoreFunctionalityTests.test_static_routes
- L92: [method] CoreFunctionalityTests.test_api_projects_endpoint
- L117: [method] CoreFunctionalityTests.test_create_project_form
- L136: [method] CoreFunctionalityTests.run_all_tests

### tests/test_doctor_mode.py
- L16: [function] test_doctor_mode_runs

### tests/test_embedded_qt_ui.py
- L14: [function] _free_port
- L26: [function] test_embedded_qt_upload_flow

### tests/test_file_llm.py
- L14: [function] _reload_app_with_temp_env_llm
- L33: [function] _create_project
- L46: [function] _resolve_branch_ids
- L55: [function] test_upload_emits_processing_and_updates_metadata_json
- L98: [function] test_upload_sets_ai_fields_via_llm
- L140: [function] test_thread_chat_llm_generates_assistant_message

### tests/test_html_rendering.py
- L14: [function] test_projects_list_html_formats_datetime
- L16: [nested_function] test_projects_list_html_formats_datetime.__init__

### tests/test_local_tool_exec.py
- L20: [function] _start_server
- L46: [function] _stop_server
- L57: [function] _free_port
- L67: [function] test_tool_exec_db_code_web_locally

### tests/test_playwright_changelog.py
- L13: [function] _find_free_port
- L21: [function] _start_server
- L51: [function] _stop_server
- L63: [function] test_changelog_page_is_not_merge

### tests/test_playwright_chat_ack.py
- L14: [function] _find_free_port
- L22: [function] _start_server
- L53: [function] _stop_server
- L65: [function] test_chat_processing_ack_and_final

### tests/test_playwright_chat_submit.py
- L14: [function] _find_free_port
- L22: [function] _start_server
- L52: [function] _stop_server
- L64: [function] test_chat_submit_triggers_processing_and_submitted

### tests/test_playwright_merge.py
- L13: [function] _find_free_port
- L21: [function] _start_server
- L49: [function] _stop_server
- L61: [function] test_merge_dashboard_shows_unique_and_merges

### tests/test_playwright_shell.py
- L12: [function] _find_free_port
- L20: [function] _start_server
- L50: [function] _stop_server
- L62: [function] test_shell_ui_open_world

### tests/test_playwright_upload.py
- L15: [function] _find_free_port
- L23: [function] _start_server
- L51: [function] _stop_server
- L63: [function] test_project_upload_flow

### tests/test_playwright_upload_chat_ack.py
- L13: [function] _find_free_port
- L21: [function] _start_server
- L51: [function] _stop_server
- L63: [function] test_upload_autochat_shows_processing_filename

### tests/test_project_management.py
- L21: [method] ProjectManagementTests.__init__
- L28: [method] ProjectManagementTests.test_list_projects
- L55: [method] ProjectManagementTests.test_create_project
- L100: [method] ProjectManagementTests._find_created_project
- L115: [method] ProjectManagementTests.test_open_project
- L156: [method] ProjectManagementTests.test_project_api_operations
- L184: [method] ProjectManagementTests.test_delete_project
- L209: [method] ProjectManagementTests.run_all_tests

### tests/test_project_page_percent_signs.py
- L9: [function] test_project_page_renders_with_percent_signs

### tests/test_qt_stale_lock_recovery.py
- L14: [function] test_qt_stale_lock_recovery

### tests/test_shell_grep.py
- L7: [function] _prep_env
- L22: [function] test_shell_grep_demo

### tests/test_smoke.py
- L10: [function] test_home_ok
- L19: [function] test_create_and_open_project

### tests/test_threads_new_json.py
- L10: [function] _reload_app_with_env
- L20: [function] _cleanup
- L27: [function] test_threads_new_json_endpoint_returns_json_response

### tests/test_tool_functions.py
- L29: [function] _reload_app_isolated_env
- L39: [function] _cleanup_tmp
- L46: [function] _create_project
- L56: [function] _upload_file
- L68: [function] _last_file_id
- L85: [function] test_tools_end_to_end

### tests/test_websocket_chat.py
- L24: [method] WebSocketChatTests.__init__
- L29: [method] WebSocketChatTests.test_websocket_connection
- L51: [method] WebSocketChatTests.test_simple_message
- L95: [method] WebSocketChatTests.test_math_question
- L164: [method] WebSocketChatTests.test_simple_arithmetic
- L215: [method] WebSocketChatTests.test_websocket_streaming
- L263: [method] WebSocketChatTests.run_all_tests
- L320: [function] run_websocket_tests

### tests/test_websockets.py
- L18: [function] _reload_app_with_temp_env
- L34: [function] _cleanup_temp_env
- L41: [function] test_ws_end_to_end_shell_and_sql_and_branches

### thinker.py
- L38: [method] Thinker.__init__
- L42: [method] Thinker.think
- L120: [method] Thinker.parse_thinking_output

## Duplicate simple names across modules
- __init__ (57 occurrences):
  - agents/__init__.py L18 qual=PlanAgent.__init__
  - agents/__init__.py L29 qual=WebAgent.__init__
  - agents/__init__.py L40 qual=FileAgent.__init__
  - agents/__init__.py L51 qual=DbAgent.__init__
  - agents/__init__.py L62 qual=NotesAgent.__init__
  - agents/__init__.py L73 qual=ImagesAgent.__init__
  - agents/__init__.py L84 qual=QuestionAgent.__init__
  - agents/base_agent.py L40 qual=BaseAgent.__init__
  - agents/code.py L23 qual=CodeAgent.__init__
  - agents/final.py L14 qual=FinalAgent.__init__
  - cedar_app/llm/client.py L36 qual=_llm_client_config.__init__
  - cedar_app/llm/client.py L39 qual=_llm_client_config.__init__
  - cedar_app/llm/client.py L42 qual=_llm_client_config.__init__
  - cedar_app/llm/client.py L132 qual=_llm_client_config.__init__
  - cedar_app/llm/client.py L135 qual=_llm_client_config.__init__
  - cedar_app/llm_utils.py L59 qual=llm_client_config.__init__
  - cedar_app/llm_utils.py L62 qual=llm_client_config.__init__
  - cedar_app/llm_utils.py L65 qual=llm_client_config.__init__
  - cedar_app/llm_utils.py L154 qual=llm_client_config.__init__
  - cedar_app/llm_utils.py L157 qual=llm_client_config.__init__
  - cedar_app/shell_utils.py L30 qual=ShellJob.__init__
  - cedar_app/shell_utils.py L207 qual=ShellJobManager.__init__
  - cedar_app/tools/shell.py L23 qual=ShellJob.__init__
  - cedar_app/utils/chat_persistence.py L20 qual=ChatManager.__init__
  - cedar_orchestrator/advanced_orchestrator.py L73 qual=ShellAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L400 qual=CodeAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L613 qual=ReasoningAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L712 qual=SQLAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L866 qual=GeneralAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L965 qual=MathAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L1053 qual=ResearchAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L1147 qual=StrategyAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L1240 qual=DataAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L1358 qual=FileAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L1587 qual=NotesAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L1687 qual=ChiefAgent.__init__
  - cedar_orchestrator/advanced_orchestrator.py L2115 qual=ThinkerOrchestrator.__init__
  - cedar_orchestrator/chief_agent_notes.py L18 qual=ChiefAgentNoteTaker.__init__
  - cedar_orchestrator/file_processing_agents.py L64 qual=FileReaderAgent.__init__
  - cedar_orchestrator/file_processing_agents.py L155 qual=PDFExtractionAgent.__init__
  - cedar_orchestrator/file_processing_agents.py L248 qual=OCRAgent.__init__
  - cedar_orchestrator/file_processing_agents.py L326 qual=LangExtractAgent.__init__
  - cedar_orchestrator/file_processing_agents.py L381 qual=ImageAnalysisAgent.__init__
  - cedar_orchestrator/file_processing_agents.py L478 qual=SQLMetadataAgent.__init__
  - cedar_orchestrator/file_processing_agents.py L630 qual=FileProcessingOrchestrator.__init__
  - cedar_orchestrator/ws_chat.py L24 qual=WSDeps.__init__
  - cedar_orchestrator/ws_chat.py L163 qual=handle_ws_chat.__init__
  - cedarqt.py L295 qual=LoggingWebPage.__init__
  - cedarqt.py L528 qual=_launch_server_inprocess.__init__
  - scripts/run_llm_tool_audit.py L145 qual=App.__init__
  - test_orchestrator.py L17 qual=MockWebSocket.__init__
  - tests/run_all_tests.py L26 qual=CedarPyTestRunner.__init__
  - tests/test_core_functionality.py L14 qual=CoreFunctionalityTests.__init__
  - tests/test_html_rendering.py L16 qual=test_projects_list_html_formats_datetime.__init__
  - tests/test_project_management.py L21 qual=ProjectManagementTests.__init__
  - tests/test_websocket_chat.py L24 qual=WebSocketChatTests.__init__
  - thinker.py L38 qual=Thinker.__init__

[...truncated duplicate list for brevity in this doc; see script output for full detail...]

---

## Execution Timeline: What runs when a user submits a prompt

This outlines the exact flow for WebSocket chat, with file paths and key function names.

1) WebSocket route registration and entry
- File: cedar_orchestrator/ws_chat.py
  - register_ws_chat() registers /ws/chat/{project_id} and /ws/chat.
  - handle_ws_chat(websocket, orchestrator, project_id, deps) is the entry point for each WS connection.

2) Message receipt and chat persistence
- handle_ws_chat:
  - Accepts the WebSocket.
  - On message {type: 'message', content: ...}:
    - Creates or loads a chat via cedar_app.utils.chat_persistence.ChatManager (create_chat, add_message).
    - Sets status 'processing'.
    - Wraps the websocket in a PersistentWebSocket that persists outgoing 'message' and 'final' to the chat DB.
    - Creates a DB session for notes (optional) and calls orchestrator.orchestrate(...).

3) Orchestrator: Think → Plan → Execute (agents) → Decide
- File: cedar_orchestrator/advanced_orchestrator.py
- ThinkerOrchestrator.think(message):
  - Classifies the query (e.g., simple_calculation), selects minimal agents (e.g., ['CodeAgent']).
  - Emits an 'action' event with function='processing' and a rich analysis block (Chief Agent Analysis, Agent Assignments).
- ThinkerOrchestrator.orchestrate(...):
  - Builds the agent list from thinking (CodeAgent, ReasoningAgent, etc.).
  - Runs them in parallel with asyncio.gather.
  - For each AgentResult, sends type='agent_result' with agent_name=result.display_name (e.g., 'Coding Agent') and the full formatted result text.
- ChiefAgent.review_and_decide(...):
  - Reviews all agent outputs (and prior iteration context if any), may call the LLM, and returns a decision JSON containing:
    - decision: 'final' | 'loop' | 'clarify'
    - final_answer: formatted text with Answer / Why / Potential Issues / Suggested Next Steps
    - selected_agent, reasoning, etc.
  - Orchestrator formats the final text and sends type='final' with json.function='orchestration_complete'.

4) Frontend rendering and timer control
- File: cedar_app/utils/page_rendering.py
- Key behaviors:
  - On type='action' ('processing'): creates a 'Chief Agent' bubble with spinner and sets a running timer.
  - On type='agent_result': creates a clickable bubble per agent, showing a collapsed 'Answer' line and allowing details toggle.
  - On type='final':
    - Sets finalOrError = true and clears any timeout and spinner.
    - Renders a final assistant bubble titled by json.function (e.g., 'orchestration_complete').
    - Synthesizes an 'Assistant' prompt JSON bubble if one was not displayed earlier (for prompt drilldown), which explains the 'Assistant / Prepared LLM prompt' you sometimes see before the final.

5) Persistence and completion
- In ws_chat.py’s PersistentWebSocket.send_json:
  - type='final' messages are persisted with metadata={'type': 'final_answer'} and the chat status set to 'complete'.

Notes on agent naming in UI
- The agent_result display uses result.display_name from each agent’s implementation in advanced_orchestrator.py (e.g., 'Coding Agent'). If you saw 'Code Executor' previously, that came from an older orchestrator build; the live code now emits 'Coding Agent'.

---

## Regeneration
- This file’s function index was generated by scanning the code with Python’s ast module, excluding vendor and build directories.
- To refresh after code changes, re-run the generator script used in this session or integrate it into a make/CI step.