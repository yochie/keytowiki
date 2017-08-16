import pywikibot
import music21
import pagefromfile
import os
import mido
import time
from tkinter import Tk, Label, Button, Toplevel
from mido import Message, MidiFile, MidiTrack
from music21 import converter
from music21.ext.six import StringIO
import webbrowser
import upload
from tkinter import *

experimental = True
bpm = 90
startpath =  os.getcwd()

#Soon to be removed...
#Need to add port selection to the GUI
portkeywords = ['loopMIDI', 'Midi']


def main():
	root = Tk()
	recordingGui = RecordingGui(root)
	root.mainloop()

class RecordingGui:
	def __init__(self, master):

		self.master = master
		master.title("Record music!")

		self.greet_button = Button(master, text="Start recording", command=self.recordStart)
		self.greet_button.pack()

		self.greet_button = Button(master, text="End recording", command=self.recordEnd)
		self.greet_button.pack()

		#Chronometer - TODO
		# self.label = Label(master, text="Recording time: 00:00")
		# self.label.pack()

		self.close_button = Button(master, text="Close", command=master.quit)
		self.close_button.pack()

	def recordStart(self):
		print("start rec!")
		
		self.mid = music21.midi.MidiFile()
		self.mid.ticksPerQuarterNote = 2048

		self.track = music21.midi.MidiTrack(0)

		mm = music21.tempo.MetronomeMark(number=bpm)

		#create list of tempo indicating events
		events = music21.midi.translate.tempoToMidiEvents(mm)

		#read mspqn from create events
		self.microSecondsPerQuarterNote = music21.midi.getNumber(events[1].data, len(events[1].data))[0]

		#link structures
		self.track.events.extend(events)
		self.mid.tracks.append(self.track)


		self.first=True

		#open ports
		portnames = mido.get_input_names()
		print(portnames)
		
		#TODO: add way to choose port from gui
		filteredportnames = [i for i in portnames if True in [portkeyword in i for portkeyword in portkeywords]]

		#choose last port from list of available, this is bad behaviour...
		if len(filteredportnames) > 0 :
			portname = filteredportnames[-1]
			self.inport = mido.open_input(name=portname)
			self.inport.callback = self.saveMyMessage
			print('Using port : ' + portname)
		else:
			print('Closing application : No available ports')
			self.master.quit()


	def saveMyMessage(self, msg):
		if (msg.type == 'note_on' or msg.type =='note_off') :
			#EXPERIMENTAL VERSION WITH TIMING
			if (experimental) :

				#convert time difference to ticks using tempo information
				delta = int( mido.second2tick(time.perf_counter(), self.mid.ticksPerQuarterNote , self.microSecondsPerQuarterNote))

				#limit to whole note
				if (delta > self.mid.ticksPerQuarterNote*4) :
					delta =  int(self.mid.ticksPerQuarterNote*4)

				#round
				delta = int (RecordingGui.roundToMultiples(delta,  self.mid.ticksPerQuarterNote/4))

				#SPECIAL CASES
				#set first time to 1 beat
				if (self.first) :
					delta =  int(self.mid.ticksPerQuarterNote)
					self.first = False

				#if note_off msg of a very short message, set min duration of 16th note
				#skip first one because prevnote will be null
				#note_on msg seem to be delayed automatically by 16th note from eachother by music21, so no need to do that
				else :
					if ((msg.type == 'note_off') and (msg.note == self.prevnote) and (delta == 0)) : 
						delta =  int(self.mid.ticksPerQuarterNote/4)
						#print(msg.type)

				#update prevnote for checking for short notes
				self.prevnote = msg.note

				#for debug
				#print(delta)

			#FIXED TIMING VERSION (EXPERIMENTAL = False)
			else :
				if msg.type == 'note_on' : 
					delta = 0
				else :
					delta = 1024

			#DELTA TIME MSG
			dt = music21.midi.DeltaTime(self.track)
			dt.time = delta

			self.track.events.append(dt)

			#NOTE MSG
			m21msg = music21.midi.MidiEvent(self.track)
			m21msg.type = msg.type.upper()
			m21msg.time = None
			m21msg.pitch = msg.note
			m21msg.velocity = msg.velocity
			m21msg.channel = 1
			self.track.events.append(m21msg)

		#for debug
		print(m21msg)
		

	def recordEnd(self):
		print("end rec!")

		#END OF TRACK
		dt = music21.midi.DeltaTime(self.track)
		dt.time = 0
		self.track.events.append(dt)
		me = music21.midi.MidiEvent(self.track)
		me.type = "END_OF_TRACK"
		me.channel = 1
		me.data = ''
		self.track.events.append(me)
		print(self.mid)

		#close port
		self.inport.callback = None
		self.inport.close()

		#Create MIDI file  from mystream
		songname = 'new_song.mid'
		filepath = os.path.join(startpath, songname)
		self.mid.open(filepath, 'wb')
		self.mid.write()
		self.mid.close()
		mystream = music21.midi.translate.midiFileToStream(self.mid)
		
		print("Plain :\n")
		mystream.show('text', addEndTimes=True)

		print("Flat :\n")
		flatstream =  mystream.flat
		flatstream.show('text', addEndTimes=True)

		print("Just notes:\n")
		justnotes = flatstream.notesAndRests.stream()
		justnotes.show('text', addEndTimes=True)

		print("Just notes with chords:\n")
		justnoteswithchords = justnotes.chordify()
		justnoteswithchords.show('text', addEndTimes=True)


		print("Just notes with chords and rests:\n")
		justnoteswithchords.makeRests()
		justnoteswithchords.show('text', addEndTimes=True)


		#go through list of events and set end time of events to  whevener another event starts
		#if two notes start at same time, then they must end at same time
		firstNote = True
		prevnotewaschord = False
		for mynote in justnoteswithchords:
			if firstNote :
				firstNote = False
				prevnote = mynote
			else:
				#if two notes start at same time, then they must end at same time
				if prevnote.offset == mynote.offset :
					#take the duration of previous note in chords, ie chords will cut off when their first note is unpressed
					mynote.duration = prevnote.duration
					prevnotewaschord = True
				else:	
					if prevnotewaschord :
						mynote.offset = prevnote.offset + prevnote.duration.quarterLength
						prevnotewaschord = False

					else :
						prevnote.duration = music21.duration.Duration(mynote.offset - prevnote.offset)
				
				prevnote = mynote
		
		print("No overlap:\n")
		justnoteswithchords.show('text', addEndTimes=True)

		mystream = justnoteswithchords

		print("Fixed mystream:\n")
		mmystream = mystream.makeMeasures()
		fmmystream = mmystream.makeNotation()
		fmmystream.show('text', addEndTimes=True)


		#compute filepath - TODO: change to cl argument
		scorename = 'new_score'
		filepath = os.path.join(startpath, scorename)
		#print('creating score at : ' + filepath + '.png')

		#Create score PNG file
		conv =  music21.converter.subConverters.ConverterLilypond()
		conv.write(fmmystream, fmt = 'lilypond', fp=filepath, subformats = ['png'])

		#Open form window to input title and launch upload
		self.newWindow = Toplevel()
		self.formGui = FormGui(self.newWindow)

	#Helper function to round ticks to closest 1/16 note
	def roundToMultiples(toRound, increment) :
		if (toRound%increment >= increment/2) : 
			rounded = toRound + (increment-(toRound%increment))
		else :
			rounded = toRound - (toRound%increment)

		#print ('rounding {} to {}'.format(toRound, rounded))
		return rounded


class FormGui:
	def __init__(self, master):
		self.master = master
		master.title("Formulaire d'import")

		#field name
		self.label = Label(master, text="Donnez un titre à la page")
		self.label.pack()

		#field content
		self.titleString = StringVar()
		self.titleString.set("")
		self.titleField = Entry(master, textvariable=self.titleString)
		self.titleField.pack()

		#button
		self.formbutton = Button(master, text="Ajouter au wiki", command=self.doneForm)
		self.formbutton.pack()
		

	def doneForm(self):
		print("Uploading info!")
		self.title = self.titleString.get()

		#upload fichier MIDI
		upload.main('-always','-filename:' + self.title + '.mid', '-ignorewarn', '-noverify','new_song.mid','-putthrottle:1','''{{Fichier|Concerne=''' + self.title +'''|Est un fichier du type=MIDI}}''')

		#upload fichier score
		upload.main('-always','-filename:' + self.title + '.png', '-ignorewarn', '-noverify','new_score.png','-putthrottle:1','''{{Fichier|Concerne=''' + self.title +'''|Est un fichier du type=Score}}''')

		#Open page on wiki to input more info
		webbrowser.open("http://leviolondejos.wiki/index.php?title=Spécial:AjouterDonnées/Enregistrement/" + self.title)

		#close
		self.master.destroy()
		

if __name__ == '__main__':
	main()
