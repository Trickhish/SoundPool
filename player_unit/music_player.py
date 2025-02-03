import asyncio


class AsyncPlayer:
    def __init__(self):
        self.playlist = []  # List of MP3 file paths
        self.current_index = 0
        self.playing = False
        self.current_audio = None
        self.playback_obj = None

    async def play(self):
        """Play the current song."""
        if not self.playlist:
            print("Playlist is empty!")
            return

        # Load the current track
        current_file = self.playlist[self.current_index]
        print(f"Playing {current_file}...")
        audio = AudioSegment.from_mp3(current_file)
        self.current_audio = audio

        # Play the audio asynchronously
        self.playing = True
        self.playback_obj = sa.play_buffer(audio.raw_data, num_channels=audio.channels,
                                           bytes_per_sample=audio.sample_width, sample_rate=audio.frame_rate)
        await asyncio.sleep(audio.duration_seconds)

    def pause(self):
        """Pause the current song."""
        if self.playing and self.playback_obj:
            print("Pausing playback.")
            self.playback_obj.stop()
            self.playing = False

    async def next_song(self):
        """Skip to the next song in the playlist."""
        if not self.playlist:
            print("Playlist is empty!")
            return

        self.current_index = (self.current_index + 1) % len(self.playlist)
        print(f"Skipping to next song: {self.playlist[self.current_index]}")
        if self.playing:
            self.pause()
        await self.play()

    async def previous_song(self):
        """Go to the previous song in the playlist."""
        if not self.playlist:
            print("Playlist is empty!")
            return

        self.current_index = (self.current_index - 1) % len(self.playlist)
        print(f"Going back to previous song: {self.playlist[self.current_index]}")
        if self.playing:
            self.pause()
        await self.play()

    def go_to_timestamp(self, timestamp: float):
        """Go to a specific timestamp in the current song."""
        if self.current_audio and self.playing:
            # Pause, seek to timestamp, and resume
            self.pause()
            print(f"Going to {timestamp} seconds in {self.playlist[self.current_index]}...")
            play_duration = self.current_audio.duration_seconds
            if timestamp < play_duration:
                # Slice the audio from the timestamp onwards
                sliced_audio = self.current_audio[timestamp * 1000:]
                self.current_audio = sliced_audio
                self.playback_obj = sa.play_buffer(sliced_audio.raw_data,
                                                   num_channels=sliced_audio.channels,
                                                   bytes_per_sample=sliced_audio.sample_width,
                                                   sample_rate=sliced_audio.frame_rate)
                self.playing = True
            else:
                print(f"Timestamp {timestamp} exceeds track duration.")
        else:
            print("No audio is playing.")

    def add_to_playlist(self, file_path: str):
        """Add a new MP3 file to the playlist."""
        if os.path.exists(file_path):
            self.playlist.append(file_path)
            print(f"Added {file_path} to the playlist.")
        else:
            print(f"File {file_path} does not exist.")

    def get_playlist(self):
        """Return the current playlist."""
        return self.playlist


async def runPlayer(player):
    player.add_to_playlist('songs/1.mp3')
    player.add_to_playlist('songs/2.mp3')
    player.add_to_playlist('songs/3.mp3')

    await player.play()

    await asyncio.sleep(5)
    player.pause()
    await asyncio.sleep(2)
    await player.next_song()
    await asyncio.sleep(3)
    player.go_to_timestamp(10)

    player.add_to_playlist('song3.mp3')

    await asyncio.sleep(3)