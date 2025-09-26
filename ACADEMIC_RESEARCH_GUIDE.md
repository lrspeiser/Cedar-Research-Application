# Cedar Academic Research Guide

## Overview

Cedar has been optimized to assist academics with rigorous research that meets publication standards. The system prioritizes **reproducibility**, **citations**, and **structured data** to ensure all work can be peer-reviewed and replicated.

## Core Principles

### 1. Reproducibility First
- **All computations use code**: Every calculation, analysis, or data transformation is performed using Python code that others can run
- **Documented parameters**: All assumptions, parameters, and methods are documented in code comments
- **Version control**: All code is saved and tracked in git for complete reproducibility

### 2. Structured Data Management
- **Automatic database creation**: Raw data files (CSV, JSON, Excel) are automatically structured into SQL databases
- **Queryable formats**: All data is stored in formats that allow systematic querying and analysis
- **Metadata tracking**: Sources, methods, and transformations are documented in metadata tables

### 3. Comprehensive Citations
- **Literature reviews**: Research Agent finds peer-reviewed sources for all claims
- **Citation database**: References are stored in a structured database for easy management
- **Conflicting findings**: Documents disagreements in the literature for balanced perspective

### 4. Multi-Agent Collaboration
The Chief Agent coordinates multiple specialized agents simultaneously:

#### Understanding Agent Capabilities (CRITICAL!)

**💻 Code Agent**: 
- ✅ CAN: Write/execute Python code, calculations, data analysis, visualizations
- ❌ CANNOT: Access files on disk or run shell commands
- USE FOR: All computations and statistical analysis

**🖥️ Shell Agent** (ONLY agent that can search your computer!):
- ✅ CAN: Execute ANY shell command (`find`, `grep`, `ls`, `cat`, etc.)
- ✅ CAN: Search for files: `find ~ -name "*keyword*"`
- ✅ CAN: Search file contents: `grep -r "pattern" /path`
- USE FOR: Finding files on your machine, system operations

**🗄️ SQL Agent**:
- ✅ CAN: Create databases, tables, execute SQL queries
- ❌ CANNOT: Search filesystem
- USE FOR: Structuring data into queryable databases

**📚 Research Agent**:
- ✅ CAN: Find academic papers and build citations
- ❌ CANNOT: Download actual papers
- USE FOR: Building bibliographies and literature reviews

**📝 Notes Agent**:
- ✅ CAN: Create structured documentation
- ❌ CANNOT: Search for information
- USE FOR: Documenting methodology and findings

**📥 File Agent** (URL downloader ONLY!):
- ✅ CAN: Download files from URLs
- ❌ CANNOT: Search your computer for files
- USE FOR: ONLY downloading from the internet

**🔬 Math Agent**:
- ✅ CAN: Derive formulas and write proofs
- ❌ CANNOT: Execute calculations (use Code Agent)
- USE FOR: Mathematical derivations and theorem proofs

## Research Workflow

### Starting a Research Project

1. **Upload your data files**
   - System automatically extracts content and creates structured schemas
   - Data is converted to SQL databases for querying

2. **Define your research question**
   - Be specific about hypotheses and objectives
   - System will create a comprehensive research plan

3. **Let the multi-agent system work**
   - Multiple agents work in parallel
   - System uses all available iterations for thoroughness
   - Each step is documented for reproducibility

### Example Research Requests

#### Data Analysis Request
```
"Analyze this dataset.csv for correlations between variables X and Y, 
create visualizations, and find relevant literature on this relationship"
```

The system will:
1. Load data into a structured SQL database
2. Write Python code for statistical analysis
3. Generate reproducible visualizations
4. Find peer-reviewed papers on the topic
5. Document all methods and limitations

#### Literature Review Request
```
"Create a literature review on machine learning applications in biology
with a focus on protein folding"
```

The system will:
1. Search for relevant academic sources
2. Create a citation database
3. Document conflicting findings
4. Generate a structured bibliography
5. Save all references in queryable format

#### Computational Research Request
```
"Implement and compare three different clustering algorithms on my dataset,
with statistical validation of results"
```

The system will:
1. Write reproducible code for each algorithm
2. Implement statistical tests
3. Store results in structured database
4. Create comparison visualizations
5. Document methodology and assumptions

## Quality Standards Checklist

The Chief Agent ensures all research meets these standards:

✅ **Reproducible Code**: Every computation has code that others can run
✅ **Structured Data**: All data in queryable database format
✅ **Citations**: All claims backed by credible sources
✅ **Methodology**: Fully documented procedures
✅ **Verification**: Multiple methods used when possible
✅ **Limitations**: Explicitly stated assumptions and biases

## Advanced Features

### Iterative Refinement
- System uses ALL available iterations (up to 10) for thoroughness
- Automatically re-runs analyses with different approaches if results are inconsistent
- Asks for user clarification if stuck after multiple attempts

### Shell Command Documentation
When system commands are needed:
```
"Install the required Python packages for statistical analysis"
```

The Shell Agent will:
1. Execute exact commands: `pip install pandas scipy statsmodels matplotlib`
2. Document the setup process
3. Create a requirements file for reproducibility

### Database Schema Creation
For any uploaded data, the system automatically:
1. Analyzes structure and content
2. Creates normalized SQL schemas
3. Generates data dictionaries
4. Implements foreign key relationships
5. Creates indexes for performance

## Best Practices

### 1. Be Specific About Requirements
Instead of: "Analyze my data"
Use: "Perform regression analysis on variables A, B, C with significance testing and residual plots"

### 2. Request Multiple Verification Methods
Ask for: "Verify these results using both parametric and non-parametric tests"

### 3. Ask for Citations
Include: "Find peer-reviewed sources supporting this methodology"

### 4. Request Documentation
Specify: "Document all assumptions and limitations of this analysis"

## Output Format

All research outputs include:

### Results Section
- Key findings with statistical significance
- Visualizations with reproducible code
- Tables in structured format

### Methodology Section
- Step-by-step procedures
- Code snippets for replication
- Parameter choices and justifications

### Citations Section
- Full bibliography in standard format
- Links to sources when available
- Notes on conflicting findings

### Code/Data Section
- Complete Python scripts
- SQL schemas and queries
- Data transformation pipelines

### Limitations Section
- Assumptions made
- Potential biases
- Scope restrictions

### Suggested Next Steps
- Follow-up analyses
- Additional data needs
- Research extensions

## Troubleshooting

If the system gets stuck:
1. It will attempt multiple approaches automatically
2. After several failed attempts, it will ask for user guidance
3. You can provide additional context or alternative approaches
4. The system documents all attempts for learning

## Integration with Academic Workflow

### Export Options
- Markdown reports for papers
- SQL databases for data sharing
- Python notebooks for reproducibility
- Citation lists for bibliography managers

### Collaboration Features
- All work saved in git
- Clear documentation for team members
- Structured data for sharing
- Reproducible analysis pipelines

---

For questions or feature requests, please refer to the main README or submit an issue on GitHub.