#!/usr/bin/env python3
"""
Migratie script om bestaande chat messages van PostgreSQL naar S3 te verplaatsen
"""

from main import app, db, Chat, Message, s3_service
from datetime import datetime

def migrate_chats_to_s3():
    """Migreer alle chats van PostgreSQL naar S3"""
    
    with app.app_context():
        # Haal alle chats op die nog niet naar S3 zijn gemigreerd
        chats = Chat.query.filter(Chat.s3_messages_key == None).all()
        
        print(f"Gevonden {len(chats)} chats om te migreren naar S3...")
        
        migrated = 0
        failed = 0
        
        for chat in chats:
            try:
                # Haal alle messages voor deze chat op
                messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at).all()
                
                if not messages:
                    print(f"  Chat {chat.id}: Geen messages, overslaan")
                    continue
                
                # Converteer messages naar dict format voor S3
                messages_data = []
                for msg in messages:
                    msg_dict = {
                        'role': msg.role,
                        'content': msg.content,
                        'created_at': msg.created_at.isoformat(),
                        'feedback_rating': msg.feedback_rating
                    }
                    messages_data.append(msg_dict)
                
                # Sla messages op in S3
                s3_key = s3_service.save_chat_messages(
                    chat_id=chat.id,
                    tenant_id=chat.tenant_id,
                    messages=messages_data
                )
                
                if s3_key:
                    # Update chat record
                    chat.s3_messages_key = s3_key
                    chat.message_count = len(messages_data)
                    db.session.commit()
                    
                    print(f"  Chat {chat.id}: {len(messages_data)} messages gemigreerd naar S3")
                    migrated += 1
                else:
                    print(f"  Chat {chat.id}: FOUT - S3 upload gefaald")
                    failed += 1
                    
            except Exception as e:
                print(f"  Chat {chat.id}: FOUT - {str(e)}")
                failed += 1
                db.session.rollback()
        
        print(f"\nMigratie voltooid!")
        print(f"  Geslaagd: {migrated}")
        print(f"  Gefaald: {failed}")
        print(f"\nNOTE: Oude messages blijven in PostgreSQL voor safety.")
        print(f"      Verwijder ze handmatig als je zeker weet dat S3 werkt.")

if __name__ == '__main__':
    migrate_chats_to_s3()
