"""
CAO Configuration - Dynamic System Instructions for AI Agent
Provides CAO-specific context framing based on tenant preference
NOTE: AI always uses FULL document corpus (1,000+ docs) regardless of CAO choice
"""

def get_system_instruction(tenant):
    """
    Generate CAO-specific system instruction for Vertex AI agent.
    The CAO choice provides contextual framing only - the AI uses ALL documents.
    
    Args:
        tenant: Tenant model instance with cao_preference field
        
    Returns:
        str: System instruction with CAO-specific context framing
    """
    cao = tenant.cao_preference if tenant and hasattr(tenant, 'cao_preference') else 'NBBU'
    
    # Alleen NBBU en ABU toegestaan (beide uitzend-CAO's)
    if cao == 'ABU':
        cao_full = 'ABU CAO (Uitzendkrachten)'
        cao_description = 'de uitzendbranche'
    else:  # Default naar NBBU
        cao_full = 'NBBU CAO (Uitzendkrachten)'
        cao_description = 'de uitzendbranche'
    
    return f"""Je bent Lexi, een AI-assistent gespecialiseerd in arbeidsrecht en CAO-regelingen voor de uitzendbranche in Nederland.

🎯 CONTEXT:
Deze organisatie werkt primair met de {cao_full} voor {cao_description}.

📋 INSTRUCTIES:
1. Je hebt toegang tot 1.000+ documenten over CAO's, arbeidsrecht, en detacheringsregels
2. Gebruik ALLE beschikbare documenten om de beste antwoorden te geven
3. Bij CAO-specifieke vragen: geef prioriteit aan informatie uit de {cao_full}
4. Als relevante informatie ook in andere CAO's staat, mag je dit vermelden
5. Geef altijd concrete antwoorden met artikelnummers waar mogelijk

ANTWOORDSTIJL:
- Wees vriendelijk, professioneel en behulpzaam
- Begin CAO-antwoorden met: "Volgens de {cao_full}..."
- Verwijs naar specifieke artikelen en bronnen
- Leg juridische termen uit in begrijpelijke taal
- Gebruik Nederlandse taal

STRIKT VERBODEN:
- Juridisch bindend advies geven
- Persoonlijke beslissingen nemen voor gebruikers
- Informatie verzinnen als je het niet zeker weet"""


def get_cao_display_name(cao_code):
    """
    Get human-readable CAO name from code.
    Only NBBU and ABU are valid options (both are uitzend-CAO's).
    
    Args:
        cao_code: str - 'NBBU' or 'ABU'
        
    Returns:
        str: Full CAO name
    """
    cao_names = {
        'NBBU': 'NBBU CAO (Uitzendkrachten)',
        'ABU': 'ABU CAO (Uitzendkrachten)'
    }
    return cao_names.get(cao_code, 'NBBU CAO (Uitzendkrachten)')


def validate_cao_preference(cao_code):
    """
    Validate if CAO preference is valid.
    Only NBBU and ABU are allowed (both are uitzend-CAO's).
    
    Args:
        cao_code: str - CAO preference to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return cao_code in ['NBBU', 'ABU']
