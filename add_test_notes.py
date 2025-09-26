#!/usr/bin/env python3
"""Add test notes to the database for UI testing"""

import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main_models import Note

# Database path  
db_path = './.testdata_shell/cedarpy.db'

def add_test_notes():
    """Add several test notes to the database"""
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create several test notes with different formats
    notes_data = [
        {
            'content': """## Agent Analysis Summary
            
**Query:** How to implement a binary search tree?

### Key Findings
- Binary search trees maintain sorted data efficiently
- Average time complexity: O(log n) for search, insert, delete
- Worst case (unbalanced): O(n)
            
### Implementation Notes
1. Each node has at most two children
2. Left child values < parent value
3. Right child values > parent value
4. Balance is key for performance""",
            'tags': ['code', 'algorithm', 'date:2025-09-25'],
            'created_at': datetime.now(timezone.utc) - timedelta(hours=2)
        },
        {
            'content': json.dumps({
                'themes': [
                    {
                        'name': 'Database Design',
                        'notes': [
                            'Use proper indexing for performance',
                            'Normalize to 3NF unless denormalization needed',
                            'Consider partitioning for large tables'
                        ]
                    },
                    {
                        'name': 'API Best Practices',
                        'notes': [
                            'Use RESTful conventions',
                            'Version your APIs',
                            'Include proper error handling'
                        ]
                    }
                ]
            }),
            'tags': ['database', 'api', 'architecture', 'date:2025-09-25'],
            'created_at': datetime.now(timezone.utc) - timedelta(hours=5)
        },
        {
            'content': json.dumps({
                'sections': [
                    {
                        'title': 'Performance Optimization',
                        'text': 'Focus on database query optimization and caching strategies. Profile before optimizing.'
                    },
                    {
                        'title': 'Security Considerations',
                        'text': 'Implement input validation, use parameterized queries, and follow OWASP guidelines.'
                    }
                ]
            }),
            'tags': ['performance', 'security', 'date:2025-09-24'],
            'created_at': datetime.now(timezone.utc) - timedelta(days=1)
        },
        {
            'content': """### Meeting Notes - Project Architecture Review

**Date:** September 24, 2025
**Participants:** Chief Agent analysis

#### Decisions Made:
1. Use microservices architecture for scalability
2. Implement event-driven communication between services
3. Deploy using Kubernetes for orchestration

#### Action Items:
- [ ] Create service architecture diagram
- [ ] Define API contracts between services
- [ ] Set up CI/CD pipeline

#### Next Steps:
Schedule follow-up to review implementation progress""",
            'tags': ['meeting', 'architecture', 'planning', 'date:2025-09-24'],
            'created_at': datetime.now(timezone.utc) - timedelta(days=1, hours=3)
        }
    ]
    
    print(f"Adding {len(notes_data)} test notes to the database...")
    
    for i, note_data in enumerate(notes_data, 1):
        note = Note(
            project_id=1,  # Assuming project ID 1 exists
            branch_id=1,   # Assuming branch ID 1 (Main) exists
            content=note_data['content'],
            tags=note_data['tags'],
            created_at=note_data['created_at']
        )
        session.add(note)
        print(f"  Added note {i}: {note_data['tags'][0]} note")
    
    session.commit()
    print(f"\n✓ Successfully added {len(notes_data)} test notes to the database")
    
    # Verify they were added
    total_notes = session.query(Note).count()
    print(f"Total notes in database: {total_notes}")
    
    session.close()

if __name__ == "__main__":
    add_test_notes()