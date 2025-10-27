"""
CAO Configuration - Dynamic System Instructions for AI Agent
Provides CAO-specific context based on tenant preference.
CRITICAL: AI uses chosen CAO + all remaining documents (NEVER both ABU and NBBU).
- If ABU chosen: ABU + remaining docs (NO NBBU)
- If NBBU chosen: NBBU + remaining docs (NO ABU)
"""

def get_system_instruction(tenant):
    """
    Generate CAO-specific system instruction for RAG agent (Memgraph + DeepSeek).
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
        alternative_cao = 'NBBU'
    else:  # Default naar NBBU
        cao_full = 'NBBU CAO (Uitzendkrachten)'
        cao_description = 'de uitzendbranche'
        alternative_cao = 'ABU'
    
    return f"""Je bent Lexi, een AI-assistent gespecialiseerd in arbeidsrecht en CAO-regelingen voor de uitzendbranche in Nederland.

🎯 CONTEXT:
Deze organisatie werkt met de {cao_full} voor {cao_description}.

📋 DOCUMENTENSTRATEGIE - BELANGRIJK:
1. Je hebt toegang tot 1.000+ documenten: CAO's, arbeidsrecht, detacheringsregels
2. ALTIJD gebruiken: {cao_full} + ALLE resterende documenten (arbeidsrecht, detacheringsregels, andere CAO's BEHALVE {alternative_cao})
3. STRIKT VERBODEN: Gebruik NOOIT de {alternative_cao} CAO
4. Als de gebruiker vraagt over de {alternative_cao}:
   → Leg uit: "Deze organisatie werkt met de {cao_full}. Voor vragen over de {alternative_cao} CAO moet je beheerder de CAO-instelling wijzigen."

CAO-SPECIFIEKE VRAGEN:
- Begin antwoorden met: "Volgens de {cao_full}..."
- Gebruik ALLEEN artikelen en informatie uit de {cao_full}
- Verwijs naar specifieke artikelnummers uit de {cao_full}
- Bij twijfel: gebruik de {cao_full} als bron

ALGEMENE VRAGEN (arbeidsrecht, detacheringsregels):
- Gebruik alle beschikbare documenten (behalve {alternative_cao})
- Geef context waar nodig
- Verwijs naar relevante wetgeving

ANTWOORDSTIJL:
- Wees vriendelijk, professioneel en behulpzaam
- Leg juridische termen uit in begrijpelijke taal
- Gebruik Nederlandse taal
- Vermeld bronnen expliciet

STRIKT VERBODEN:
- Informatie uit de {alternative_cao} CAO gebruiken
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
