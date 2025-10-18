"""
CAO Configuration - Dynamic System Instructions for AI Agent
Provides CAO-specific context based on tenant preference
"""

def get_system_instruction(tenant):
    """
    Generate CAO-specific system instruction for Vertex AI agent
    
    Args:
        tenant: Tenant model instance with cao_preference field
        
    Returns:
        str: System instruction tailored to the tenant's CAO preference
    """
    cao = tenant.cao_preference if tenant and hasattr(tenant, 'cao_preference') else 'NBBU'
    
    # CAO-specifieke configuratie
    cao_configs = {
        'NBBU': {
            'full': 'NBBU CAO (Metalektro - Metaal & Techniek)',
            'description': 'de metaal-, elektro- en technologische industrie'
        },
        'ABU': {
            'full': 'ABU CAO (Uitzendkrachten - Flex & Detachering)',
            'description': 'de uitzendbranche en flexwerkers'
        },
        'Hortiplan': {
            'full': 'Hortiplan CAO (Glastuinbouw)',
            'description': 'de glastuinbouwsector'
        },
        'CAO_Uitzendkrachten': {
            'full': 'CAO voor Uitzendkrachten',
            'description': 'uitzendkrachten in Nederland'
        },
        'Agrarisch': {
            'full': 'Agrarische CAO',
            'description': 'de agrarische sector'
        },
        'Overig': {
            'full': 'Nederlandse Arbeidsrecht',
            'description': 'algemeen arbeidsrecht in Nederland'
        }
    }
    
    config = cao_configs.get(cao, cao_configs['NBBU'])
    cao_full = config['full']
    cao_description = config['description']
    
    return f"""Je bent Lexi, een AI-assistent gespecialiseerd in arbeidsrecht en CAO-regelingen voor Nederland.

🎯 BELANGRIJKE CONTEXT:
Deze gebruiker werkt onder de {cao_full} voor {cao_description}.

📋 STRIKTE INSTRUCTIES:
1. Gebruik ALLEEN de {cao_full} voor CAO-specifieke vragen
2. Bij antwoorden over vakantiedagen, salaris, werktijden, onkostenvergoedingen:
   → Begin met: "Volgens de {cao_full}..."
   → Geef ALLEEN cijfers en regels uit de {cao_full}
3. Als de gebruiker vraagt over een andere CAO:
   → Leg uit dat dit account is ingesteld voor {cao_full}
   → Geef aan dat de beheerder de CAO-keuze kan wijzigen in instellingen
4. Gebruik je volledige kennisbank om de beste antwoorden te geven

GEDRAGSREGELS:
- Wees vriendelijk, professioneel en behulpzaam
- Geef concrete antwoorden met specifieke artikelnummers waar mogelijk
- Als je iets niet zeker weet, zeg dat eerlijk
- Verwijs altijd naar de specifieke CAO die van toepassing is
- Gebruik Nederlandse taal en terminologie
- Leg juridische termen uit in begrijpelijke taal

STRIKT VERBODEN:
- Juridisch bindend advies geven
- Persoonlijke beslissingen voor gebruikers nemen
- Informatie verzinnen als je het antwoord niet weet

Blijf altijd binnen de context van de {cao_full}."""


def get_cao_display_name(cao_code):
    """
    Get human-readable CAO name from code
    
    Args:
        cao_code: str - CAO code
        
    Returns:
        str: Full CAO name
    """
    cao_names = {
        'NBBU': 'NBBU CAO (Metalektro - Metaal & Techniek)',
        'ABU': 'ABU CAO (Uitzendkrachten - Flex & Detachering)',
        'Hortiplan': 'Hortiplan CAO (Glastuinbouw)',
        'CAO_Uitzendkrachten': 'CAO voor Uitzendkrachten',
        'Agrarisch': 'Agrarische CAO',
        'Overig': 'Algemeen Nederlands Arbeidsrecht'
    }
    return cao_names.get(cao_code, 'NBBU CAO (Metalektro - Metaal & Techniek)')


def validate_cao_preference(cao_code):
    """
    Validate if CAO preference is valid
    
    Args:
        cao_code: str - CAO preference to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    valid_caos = ['NBBU', 'ABU', 'Hortiplan', 'CAO_Uitzendkrachten', 'Agrarisch', 'Overig']
    return cao_code in valid_caos
