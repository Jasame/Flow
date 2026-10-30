"""Original low-stakes starting checks, not a certified CEFR examination."""
ITEMS=[
{'id':'v1','skill':'vocabulary','tier':1,'prompt':'I am tired. I need a short ____.','options':['break','chair','ticket','window'],'answer':0,'node':'tense-present'},
{'id':'g1','skill':'grammar','tier':1,'prompt':'She ____ English every day.','options':['study','studies','studying','have studied'],'answer':1,'node':'tense-present'},
{'id':'r1','skill':'reading','tier':1,'passage':'The English club meets on Tuesday at four. Bring one book. You do not need to pay.','prompt':'What should you bring?','options':['Money','Two tickets','One book','A camera'],'answer':2,'node':'tense-present'},
{'id':'l1','skill':'listening','tier':1,'passage':'The train leaves at ten fifteen. Please meet me at the station at ten.','prompt':'When should you meet the speaker?','options':['At ten','At ten fifteen','At eleven','At nine'],'answer':0,'node':'tense-present'},
{'id':'v2','skill':'vocabulary','tier':2,'prompt':'We need to clarify the instructions. Here, clarify means ____.','options':['make less useful','make clearer','make more expensive','cancel completely'],'answer':1,'node':'clause-noun'},
{'id':'g2','skill':'grammar','tier':2,'prompt':'I suggest ____ the original source first.','options':['check','to check','checking','checked'],'answer':2,'node':'nonfinite-gerund'},
{'id':'r2','skill':'reading','tier':3,'passage':'A team tested a tool during a quiet week. Replies became faster, but difficult cases were not included. They decided to gather more evidence before introducing it everywhere.','prompt':'Why was more evidence needed?','options':['The tool had never been tested','Faster replies proved all cases were solved','The first test did not cover difficult cases','Every customer rejected the tool'],'answer':2,'node':'clause-adverb'},
{'id':'g3','skill':'grammar','tier':3,'prompt':'If I had accepted that job, I ____ in London now.','options':['will be','would be','would have been yesterday','had been'],'answer':1,'node':'subjunctive-mixed'}]

# A second brief sample per input dimension; uncertainty remains explicit.
ITEMS.extend([
 {'id':'v3','skill':'vocabulary','tier':2,'prompt':'The change is temporary: it will ____.','options':['last forever','end after a limited period','become more expensive','happen every morning'],'answer':1,'node':'tense-present'},
 {'id':'g4','skill':'grammar','tier':2,'prompt':'By the time we arrived, the film ____.','options':['already starts','has already start','had already started','starting already'],'answer':2,'node':'tense-perfect'},
 {'id':'r3','skill':'reading','tier':2,'passage':'The college extended library hours during exam week. More students visited in the evening, but no information about exam results was collected.','prompt':'What can reasonably be concluded?','options':['Longer opening hours improved exam scores','Evening visits increased, but the effect on results is unknown','Every student studied at night','The library should stay open all night'],'answer':1,'node':'clause-adverb'},
 {'id':'l2','skill':'listening','tier':2,'passage':'I can send you the draft today, but the figures will not be ready until tomorrow. Please wait for the figures before you forward it.','prompt':'What should the listener do before forwarding the draft?','options':['Wait for the figures','Send it immediately today','Rewrite all the figures','Cancel the draft'],'answer':0,'node':'clause-adverb'}
])

def public():return [{k:v for k,v in p.items() if k not in ('answer','node')} for p in ITEMS]
