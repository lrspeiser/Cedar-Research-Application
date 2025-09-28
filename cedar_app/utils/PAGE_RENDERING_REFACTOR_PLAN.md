# Page Rendering Refactoring Plan

## Current State
- **File**: `cedar_app/utils/page_rendering.py`
- **Size**: 1,997 lines
- **Functions**: 2 massive functions generating HTML strings
  - `projects_list_html()` - Generates projects list page
  - `project_page_html()` - Generates project detail page (most of the file)

## Issues
1. Monolithic HTML generation in Python strings
2. Inline JavaScript mixed with Python
3. Inline CSS mixed with HTML
4. No template separation
5. Hard to maintain and modify
6. No component reusability

## Proposed New Structure

```
cedar_app/
├── templates/
│   ├── base/
│   │   ├── layout.py          # Base HTML layout wrapper
│   │   └── head.py            # HTML head elements
│   ├── components/
│   │   ├── __init__.py
│   │   ├── alerts.py          # Alert/message components
│   │   ├── buttons.py         # Button components
│   │   ├── forms.py           # Form components
│   │   ├── tables.py          # Table components
│   │   ├── tabs.py            # Tab navigation components
│   │   └── cards.py           # Card components
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── projects_list.py   # Projects list page builder
│   │   └── project_detail.py  # Project detail page builder
│   └── partials/
│       ├── __init__.py
│       ├── chat_panel.py      # Chat interface partial
│       ├── file_panel.py      # Files panel partial
│       ├── history_panel.py   # History panel partial
│       ├── code_panel.py      # Code panel partial
│       ├── database_panel.py  # Database panel partial
│       └── notes_panel.py     # Notes panel partial
├── static/
│   ├── js/
│   │   ├── chat.js           # Chat WebSocket functionality
│   │   ├── tabs.js           # Tab switching logic
│   │   ├── forms.js          # Form handling
│   │   └── project.js        # Project-specific JavaScript
│   └── css/
│       ├── chat.css          # Chat-specific styles
│       ├── components.css    # Component styles
│       └── layout.css        # Layout styles
└── rendering/
    ├── __init__.py
    ├── builder.py             # Main page builder class
    └── renderer.py            # Final rendering logic

```

## Refactoring Steps

### Phase 1: Setup Structure
1. Create directory structure
2. Set up base template system
3. Create component library

### Phase 2: Extract Components
1. Extract reusable HTML components (alerts, tables, forms)
2. Extract tab components
3. Extract card components

### Phase 3: Extract Panels
1. Extract chat panel
2. Extract file management panel
3. Extract history panel
4. Extract code panel
5. Extract database panel
6. Extract notes panel

### Phase 4: Extract JavaScript
1. Move chat WebSocket logic to chat.js
2. Move tab switching to tabs.js
3. Move form handling to forms.js
4. Create project.js for project-specific logic

### Phase 5: Create Page Builders
1. Create ProjectsListBuilder class
2. Create ProjectDetailBuilder class
3. Implement render methods using components

### Phase 6: Update Integration
1. Update imports in main.py
2. Update any other references
3. Test all functionality

## Benefits
1. **Maintainability**: Each component in its own file
2. **Reusability**: Components can be reused across pages
3. **Separation of Concerns**: HTML, CSS, and JS separated
4. **Testability**: Components can be unit tested
5. **Scalability**: Easy to add new components or pages
6. **Developer Experience**: Easier to find and modify specific parts

## Success Metrics
- [ ] No single file over 500 lines
- [ ] Clear separation of HTML, CSS, and JavaScript
- [ ] All pages render identically to before
- [ ] Improved load times (less inline code)
- [ ] Easier to add new features