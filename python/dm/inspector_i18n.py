"""The inspector's interface language. Pages are written in German and English is swapped in as they are sent.

Each pair matches a whole literal in the page source, so story text and dialogue are never touched.
"""

ENGLISH = [
    ('" von "+scored.length+" bewertet · "+worth+" lohnen sich · Stimmen fertig: "+D.ready+" von "+D.total', '" of "+scored.length+" judged · "+worth+" worth playing · voices ready: "+D.ready+" of "+D.total'),
    ('Eine Referenzgeschichte, nicht das laufende Spiel: Das Wissen rechts ist nur simuliert. Jede Zeile der Geschichte, in der Reihenfolge, in der man ihr begegnen kann. Bewerte Text und Sprecher getrennt und begründe alles, was du ablehnst. Hake rechts Tatsachen an, um zu sehen, welche Zeilen des Helden mit diesem Wissen erscheinen.', 'A reference story, not the live game: the knowledge on the right is simulated. Every line in the story, in the order you can meet it. Judge the text and the spoken delivery separately, and give a reason for anything you reject. Tick facts on the right to see which hero lines would appear with that knowledge.'),
    ('Rahmen und verborgene Wahrheit (Spoiler)', 'Frame and hidden truth (spoilers)'),
    ('Gespräche sind rot, Tatsachen hellbraun, wesentliche Tatsachen orange und echte Folgen grün. Ein durchgezogener Pfeil heißt: Ein Gespräch lehrt eine Tatsache. Ein dicker Pfeil: Eine Tatsache startet eine Szene oder löst etwas aus. Ein gepunkteter Pfeil öffnet eine Zeile des Helden, ein gekreuzter schließt eine Szene endgültig.', 'Conversations are red, facts tan, essential facts orange, and real consequences green. A solid arrow means a conversation teaches a fact. A thick arrow means a fact starts a scene or causes an effect. A dotted arrow unlocks a hero line, and a crossed arrow closes a scene off for good.'),
    ('Scrollen oder die Knöpfe zum Zoomen, ziehen zum Bewegen. Ein Klick auf ein Gespräch springt dorthin, ein Klick auf eine Tatsache zeigt ihre Herkunft.', 'Scroll or use the buttons to zoom, and drag to pan. Click a conversation to jump to it, or a fact to see where it comes from.'),
    ('<h2>Wie es sich entfalten kann</h2>', '<h2>How it can unfold</h2>'),
    ('Lade deine Bewertungen …', 'Loading your reviews…'), ('>Gespräche<', '>Conversations<'), ('Was der Spieler weiß', 'What the player knows'),
    ('Nichts bekannt (Kaltstart)', 'Nothing known (cold start)'), ('>Folgen<', '>Consequences<'),
    ('" Logikfehler":"Gesprächslogik geprüft, keine Fehler"', '" logic errors":"Conversation logic check passed"'),
    ('st.a+" angenommen"', 'st.a+" approved"'), ('st.r+" abgelehnt"', 'st.r+" rejected"'), ('"Gespeichert."', '"Saved."'),
    ('"Speichern fehlgeschlagen. Läuft der Inspektor noch?"', '"Saving failed. Is the inspector server still running?"'),
    ('"Beides annehmen":"Annehmen"', '"Approve both":"Approve"'), ('" on":""),"Annehmen")', '" on":""),"Approve")'), ('"Ablehnen")', '"Reject")'),
    ('b.textContent="Läuft"', 'b.textContent="Playing"'), ('b.textContent="Abspielen"', 'b.textContent="Play"'), ('"v play","Abspielen")', '"v play","Play")'),
    ('u?"Abspielen":"–"', 'u?"Play":"–"'), ('"keine Aufnahme"', '"no audio generated"'), ('"label","Stimme")', '"label","Voice")'),
    ('"Warum funktioniert das nicht?"', '"Why doesn\'t this work?"'), ('"Grund der Ablehnung"', '"Reason for rejecting"'),
    ('"spricht an ab "+(c.within||450)+" Einheiten"', '"starts talking within "+(c.within||450)+" units"'), ('"braucht: "+', '"needs: "+'), ('"nicht nach: "+', '"not after: "+'),
    ('key+" · Anfang"', 'key+" · opening"'), ('"Vortrag: "+', '"delivery: "+'), ('"nutzt "+f', '"uses "+f'), ('"lehrt "+f', '"teaches "+f'),
    ('"Spätere Treffen: „"', '"Later meetings: „"'), ('"Spätere Zeile"', '"Later line"'), ('"gleiche Zeile wie "', '"same line as "'), ('", dort bewertet"', '", judged there"'),
    ('ch.ends?"endet":', 'ch.ends?"ends":'), ('"braucht "+ch', '"needs "+ch'), ('" oder "', '" or "'), ('"außer "+', '"unless "+'), ('"gerade verborgen"', '"hidden right now"'),
    ('"stumm, geht zurück"', '"silent, steps back"'), ('"Dann zurück zu den Fragen in "', '"Then back to the questions in "'), ('" bewertet"', '" reviewed"'), ('" abgelehnt":""', '" rejected":""'), ('"wenn "+x', '"when "+x'),
    ('"Bewertungen konnten nicht geladen werden."', '"Could not load reviews."'), ('"Wesentlich. "', '"Essential. "'), ('"Bekannt bei: "', '"Known by: "'), ('"niemandem im Besonderen"', '"no one in particular"'),
    ('"Erfährt man von: "', '"Learned from: "'), ('"Ereignissen, nicht aus Gesprächen"', '"events in the story, not dialogue"'), ('"Öffnet: "', '"Unlocks: "'), ('"nichts direkt"', '"nothing directly"'),
    ('"Szene beginnt: "', '"Scene starts: "'), ('"Die Graph-Bibliothek konnte nicht geladen werden. Prüfe die Verbindung."', '"The graph library could not load. Check your connection."'),
    ('"Die Graph-Bibliothek konnte nicht geladen werden."', '"The graph library could not load."'), ('"Graph-Fehler: "', '"Graph error: "'),
    ('placeholder="Zeilen, Tatsachen, Sprecher suchen" aria-label="Zeilen, Tatsachen, Sprecher suchen"', 'placeholder="Search lines, facts, speakers" aria-label="Search lines, facts, speakers"'),
    ('>Alle Zeilen<', '>All lines<'), ('>Unbewertet<', '>Unreviewed<'), ('>Abgelehnt<', '>Rejected<'), ('>Ohne Aufnahme<', '>No recording<'), ('>Alle Sprecher<', '>All speakers<'),
    ('aria-label="Sprecher"', 'aria-label="Speaker"'), ('shown+" von "+total+" Zeilen"', 'shown+" of "+total+" lines"'), ('"Keine Zeile passt."', '"No line matches."'),
    # characters
    ('placeholder="Figuren und Tatsachen suchen" aria-label="Figuren und Tatsachen suchen"', 'placeholder="Search sheets and facts" aria-label="Search sheets and facts"'),
    ('Lädt …', 'Loading…'), ('"Belege ("', '"Evidence ("'), ('"Diese Datei konnte nicht gelesen werden: "', '"This file could not be read: "'), ('"Stimme "+', '"voice "+'), ('"keine Belege"', '"no evidence recorded"'), ('" erfunden"', '" invented"'),
    ('"Als Novize"', '"As a novice"'), ('"Als Feuermagier"', '"As a Fire Mage"'), ('"Hintergrund"', '"Background"'), ('"Sprache"', '"Speech"'), ('section("Wesen"', 'section("Character"'), ('"Fraktionen"', '"Factions"'), ('"Personen"', '"People"'), ('"Politik"', '"Politics"'), ('"Spielstand"', '"Game state"'),
    ('"Wie die Figur den Helden sieht"', '"How they see the hero"'), ('"Reagiert auf"', '"Reacts to"'), ('"Nicht durch die Zeilen der Figur belegt"', '"Not grounded in the character\'s lines"'), ('"Gemeinsames Wissen"', '"Shared knowledge"'), ('"Weltwissen"', '"World facts"'),
    ('" von "+DATA.facts.length+" Tatsachen"', '" of "+DATA.facts.length+" facts"'), ('DATA.facts.length+" Tatsachen"', 'DATA.facts.length+" facts"'), ('"unlesbar"', '"unreadable"'), ('"Keine Figur passt."', '"No sheet matches."'), ('"Keine Figur ausgewählt."', '"No sheet selected."'),
    ('"Die Figuren konnten nicht geladen werden. Läuft der Inspektor noch?"', '"Could not load the sheets. Is the inspector server still running?"'),
    # experiment
    ('"Die Geschichten konnten nicht geladen werden."', '"Could not load the stories."'), ('"Fehler"', '"Defects"'), ('"Wert zu spielen?"', '"Worth playing?"'), ('"Ja"', '"Yes"'), ('"Nein"', '"No"'), ('"Interesse"', '"Interest"'),
    ('"Fehler: was stimmt nicht, und welche Regel bricht es?"', '"Defects: what is wrong, and which rule does it break?"'), ('"Nächste Geschichte"', '"Next story"'), ('"Nächste ohne Urteil"', '"Next unjudged"'),
    ('"Tasten: Y oder N, 1 bis 5, Pfeile links und rechts, U für die nächste ohne Urteil."', '"Keys: Y or N, 1 to 5, left and right arrows, U for the next unjudged."'), ('"Die Geschichte wurde seit dieser Bewertung geändert."', '"This story has changed since it was scored."'),
    ('>Erneut speichern<', '>Save again<'), ('"Nicht gespeichert: "', '"Not saved: "'), ('" Geschichte(n). Läuft der Inspector noch?"', '" stories. Is the inspector still running?"'), ('"Die verborgene Wahrheit"', '"The hidden truth"'), ('"Wie es sich entfalten kann (Spoiler)"', '"How it can unfold (spoilers)"'),
    ('"Rot sind Gespräche, hellbraun Tatsachen, orange wesentliche Tatsachen, grün echte Folgen. Durchgezogen: ein Gespräch lehrt etwas. Dick: etwas startet ein Gespräch oder löst eine Folge aus. Gepunktet: öffnet eine Zeile des Helden. Gekreuzt: schliesst etwas. Klicken springt zum Gespräch oder zeigt die Tatsache; ziehen und scrollen zum Bewegen und Zoomen."', '"Conversations are red, facts tan, essential facts orange, real consequences green. Solid: a conversation teaches something. Thick: something starts a conversation or causes a consequence. Dotted: opens a hero line. Crossed: closes something. Click to jump to a conversation or show a fact; drag and scroll to move and zoom."'),
    ('"Später: "', '"Later: "'), ('"→ zurück zu "', '"→ back to "'), ('"Geschichte "+(cur+1)+" von "', '"Story "+(cur+1)+" of "'), ('"Bonus, zählt nicht fürs Experiment"', '"Bonus, does not count for the experiment"'),
    ('"Wesentliche Tatsache":"Tatsache"', '"Essential fact":"Fact"'), ('"niemandem, nie gelehrt"', '"no one, never taught"'), ('"Abspielen: "', '"Play: "'), ('"Keine Aufnahme: "', '"No recording: "'), ('"Noch keine Geschichten. Erzeuge sie zuerst, siehe docs/experiment-1.md."', '"No stories yet. Generate them first, see docs/experiment-1.md."'),
    ('"Ende"', '"End"'), ('" · braucht "', '" · needs "'), ('aria-label="Seiten"', 'aria-label="Pages"'),
    ('>Geschichtenprobe<', '>Story trial<'), ('<a href="/">Inspektor</a>', '<a href="/">Inspector</a>'), ('<a href="/characters">Figuren</a>', '<a href="/characters">Characters</a>'),
    ('<html lang="de">', '<html lang="en">'),
]

# Labels of the reference story, translated inside its data and graph. Only these whole quoted labels are swapped
# there, so the story's own dialogue cannot be caught by a short interface word such as "Ja".
LABELS = [
    ('"Kloster, nach dem Diebstahl"', '"Monastery, after the theft"'), ('"Kloster, vor dem Diebstahl"', '"Monastery, before the theft"'), ('"Kloster, beim Näherkommen"', '"Monastery, on approach"'), ('"Hafenkneipe, immer verfügbar"', '"Harbour tavern, always available"'), ('"Hafengassen, immer verfügbar"', '"Harbour alleys, always available"'),
    ('"Bis du gehst, wenn nach Hause geschickt"', '"Until you leave, if ordered home"'), ('"An der Kelter, nach der Heimkehr"', '"At the winery, after being ordered home"'), ('"Bis du gehst, wenn ausgeliefert"', '"Until you leave, if turned in"'), ('"Bis du gehst, wenn ihm geholfen wurde"', '"Until you leave, if helped"'), ('"Nachdem Tilo ausgeliefert wurde"', '"After Tilo is turned in"'), ('"Nachdem die Belohnung bezahlt wurde"', '"After the reward is paid"'), ('"Nachdem Tilo geholfen wurde"', '"After Tilo is helped"'),
    ('"Tilos Name"', '"Tilo\'s name"'), ('"Tilo fehlt"', '"Tilo is missing"'), ('"seine Weingänge"', '"his wine trips"'), ('"Silber gestohlen"', '"silver was stolen"'), ('"zwei Leuchter"', '"two candlesticks"'), ('"Belohnung ausgesetzt"', '"reward offered"'), ('"sein Vater"', '"his father"'), ('"Würfelschulden"', '"dice debt"'), ('"Spur zum Hafen"', '"try the harbour"'), ('"Anselms Angebot"', '"Anselm\'s offer"'), ('"Harek ist misstrauisch"', '"Harek is wary"'), ('"Silber an Harek verkauft"', '"silver sold to Harek"'), ('"versteckt am Hafen"', '"hiding near harbour"'), ('"am Hafen getroffen"', '"met him at the harbour"'), ('"Tilo getroffen"', '"met Tilo"'), ('"Fass-Novize getroffen"', '"met the barrel novice"'), ('"wirkte gehetzt"', '"he looked stressed"'), ('"Tilo ausgeliefert"', '"Tilo turned in"'), ('"Tilo geholfen"', '"Tilo helped"'), ('"Belohnung bezahlt"', '"reward paid"'), ('"Geheimnis erzählt"', '"secret told"'), ('"Tilo erpresst"', '"Tilo shaken down"'), ('"Tilo gestanden"', '"Tilo confessed"'),
    ('"Tilo wieder bei der Arbeit"', '"Tilo back at work"'), ('"Tilo gehorcht"', '"Tilo obeys"'), ('"Tilo verabschiedet sich"', '"Tilo says goodbye"'), ('"Tilo verspricht zu folgen"', '"Tilo promises to follow"'), ('"Der Novize an den Fässern"', '"The novice at the barrels"'), ('"Tilo vor dem Diebstahl"', '"Tilo before the theft"'), ('"Gorax beschwert sich"', '"Gorax complains"'), ('"Parlan verkündet"', '"Parlan announces"'), ('"Anselms Bitte"', '"Anselm\'s plea"'), ('"Parlan zahlt"', '"Parlan pays"'), ('"Anselm wendet sich ab"', '"Anselm turns away"'), ('"Anselms Geheimnis"', '"Anselm\'s secret"'),
    ('"versteckter Wein taucht auf"', '"hidden wine appears"'), ('"Tilo verlässt den Hafen"', '"Tilo leaves the harbour"'),
]
ENGLISH.sort(key=lambda pair: -len(pair[0]))  # longer literals first, so a short one cannot break a longer match


def translate(html, language, pairs=None):
    if language != "de":
        for german, english in ENGLISH if pairs is None else pairs:
            html = html.replace(german, english)
    return html
