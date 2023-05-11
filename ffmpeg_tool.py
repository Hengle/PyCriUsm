from itertools import chain
from subprocess import Popen, DEVNULL


def gen_ffmpeg_cmd(video, audios, subtitles, output, video_codec=('copy',), audio_codec=('copy',), before_input=(), after_input=()):
	if not audios:
		audios = {}
	if not subtitles:
		subtitles = {}
	audio_count = len(audios)
	subtitle_count = len(subtitles)
	input_cmd = gen_input(video, *audios.values(), *subtitles.values())
	map_cmd = gen_map(1 + audio_count + subtitle_count)
	audio_metadata = gen_meta_map(audios, 'a')
	subtitle_metadata = gen_meta_map(subtitles, 's')
	cmd = ('ffmpeg', '-y', *before_input, *input_cmd, *map_cmd, *chain(*audio_metadata), *chain(*subtitle_metadata),
		   '-c:v', *video_codec, '-c:a', *audio_codec, *after_input, output)
	a = Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
	a.wait()
	return cmd


def gen_meta_map(media_map, media_type):
	count = 0
	metadata = []
	for lang, _ in media_map.items():
		metadata.append(gen_metadata(media_type, count, language=lang))
		count += 1
	return metadata


def gen_input(*input_files):
	return chain(*(('-i', i) for i in input_files))


def gen_map(count):
	return chain(*(('-map', str(i)) for i in range(count)))


def gen_metadata(media_type, media_index, **kwargs):
	return chain(*((f'-metadata:s:{media_type}:{media_index}', f'{key}={value}') for key, value in kwargs.items()))

