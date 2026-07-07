from app.services.ai_reply import _HUMAN_REQUEST_RE, _AI_ESCALATION_RE


def test_human_request_re_english():
    # True positives
    assert _HUMAN_REQUEST_RE.search("Speak with your owner")
    assert _HUMAN_REQUEST_RE.search("First ask your team to contact me. Then ill share")
    assert _HUMAN_REQUEST_RE.search("i need to talk with your team")
    assert _HUMAN_REQUEST_RE.search("contact me")
    assert _HUMAN_REQUEST_RE.search("agent")
    assert _HUMAN_REQUEST_RE.search("support")
    assert _HUMAN_REQUEST_RE.search("connect me to a real person")
    assert _HUMAN_REQUEST_RE.search("connect me")

    # True negatives
    assert not _HUMAN_REQUEST_RE.search("Hello, please help")
    assert not _HUMAN_REQUEST_RE.search("no, thank you")


def test_human_request_re_romanized_indian():
    # Tamil / Tanglish
    assert _HUMAN_REQUEST_RE.search("owner-kitta pesanum")
    assert _HUMAN_REQUEST_RE.search("agent-kitta pesunum")
    assert _HUMAN_REQUEST_RE.search("call pannunga")
    assert _HUMAN_REQUEST_RE.search("connect pannu")
    assert _HUMAN_REQUEST_RE.search("agent kitta pesalaama")

    # Hindi / Hinglish
    assert _HUMAN_REQUEST_RE.search("mujhe agent se baat karni hai")
    assert _HUMAN_REQUEST_RE.search("mere ko agent se baat karwao")
    assert _HUMAN_REQUEST_RE.search("call karo")

    # Telugu / Tenglish
    assert _HUMAN_REQUEST_RE.search("call cheyandi")
    assert _HUMAN_REQUEST_RE.search("matladali")


def test_human_request_re_native_scripts():
    # Tamil
    assert _HUMAN_REQUEST_RE.search("பேச வேண்டும்")
    assert _HUMAN_REQUEST_RE.search("பேசணும்")
    assert _HUMAN_REQUEST_RE.search("பேசுங்க")
    assert _HUMAN_REQUEST_RE.search("பேசலாமா")
    assert _HUMAN_REQUEST_RE.search("அழைக்கவும்")
    assert _HUMAN_REQUEST_RE.search("தொடர்பு கொள்ளவும்")

    # Hindi
    assert _HUMAN_REQUEST_RE.search("बात करनी है")
    assert _HUMAN_REQUEST_RE.search("बात करवाओ")
    assert _HUMAN_REQUEST_RE.search("कॉल करो")

    # Telugu
    assert _HUMAN_REQUEST_RE.search("మాట్లాడాలి")
    assert _HUMAN_REQUEST_RE.search("కాల్ చేయండి")

    # Kannada
    assert _HUMAN_REQUEST_RE.search("ಮಾತನಾಡಬೇಕು")
    assert _HUMAN_REQUEST_RE.search("ಕಾಲ್ ಮಾಡಿ")

    # Malayalam
    assert _HUMAN_REQUEST_RE.search("സംസാരിക്കണം")
    assert _HUMAN_REQUEST_RE.search("വിളിക്കൂ")


def test_ai_escalation_re():
    # True positives
    assert _AI_ESCALATION_RE.search("I'll connect you with my team.")
    assert _AI_ESCALATION_RE.search("My team will assist you with the next steps.")
    assert _AI_ESCALATION_RE.search("I'll request my team to reach out to you as soon as possible.")
    assert _AI_ESCALATION_RE.search("I need to confirm with our team regarding the partial payment.")
    assert _AI_ESCALATION_RE.search("I've informed my team about your query.")
    assert _AI_ESCALATION_RE.search("They will get in touch with you shortly to discuss your request.")
    assert _AI_ESCALATION_RE.search("I'll escalate your query again.")
    assert _AI_ESCALATION_RE.search("I will get back to you")
    assert _AI_ESCALATION_RE.search("I will ask my team and respond you")

    # True negatives
    assert not _AI_ESCALATION_RE.search("Hello, how can I help you today?")
    assert not _AI_ESCALATION_RE.search("Sure, let's complete the booking.")
