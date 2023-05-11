from pathlib import Path
from os.path import splitext
from cri_usm_demuxer.demux import UsmDemuxer, pool
import json
audio_lang = ('Chinese', "English", "Japanese", "Korean")


class Trans:
	def __init__(self, path):
		if isinstance(path, (bytes, bytearray)):
			tmp_map = json.loads(path)
		else:
			with open(path, encoding='utf-8') as f:
				tmp_map = json.load(f)
		text_map = {}
		for key, value in tmp_map.items():
			text_map[int(key)] = value
		self.text_map = text_map

	def __getitem__(self, item):
		return self.text_map.get(item, '')

	def get(self, item):
		return self.__getitem__(item)


class SRTrans(Trans):
	def __getitem__(self, item):
		if isinstance(item, dict):
			return self.text_map.get(int(item['Hash']), '')
		return item


def get_usm_decrypt_key(video_name: str, version_key: int):
	pass


def test1_wrap(input_path, video_name, version_key, output):
	if version_key == 0:
		key = 0
	else:
		key = get_usm_decrypt_key(video_name, version_key)
	a = UsmDemuxer(input_path, key, True)
	return a.export(output)


def sec_to_time(second: str):
	point_index = second.find('.')
	if point_index == -1:
		ms = '000'
		seconds = int(second)
	else:
		ms = second[point_index + 1:] + '0' * (3 - len(second) + point_index + 1)
		seconds = int(second[:point_index])
	minutes, seconds = divmod(seconds, 60)
	hours, minutes = divmod(minutes, 60)
	return '%02d:%02d:%02d,%s' % (hours, minutes, seconds, ms)


def fast_make_dir(*dirs):
	import os
	for i in dirs:
		os.makedirs(i, exist_ok=True)


def caption2srt(caption_path: Path, trans: dict, output: Path):
	def core(data, srt_path, trans_map):
		with open(srt_path, 'w', encoding='utf-8') as f:
			for count, data in enumerate(data, 1):
				f.write(f'{count}\n{data[0]} --> {data[1]}\n{trans_map[data[2]]}\n\n')

	with open(caption_path, 'rb') as f:
		data = json.load(f, parse_float=str, parse_int=str)['CaptionList']
	srts = {}
	cache_data = []
	for i in data:
		cache_data.append((sec_to_time(i["StartTime"]), sec_to_time(i["EndTime"]), i["CaptionTextID"]))
	del data
	for lang, trans_map in trans.items():
		srt_path = output / f'{caption_path.stem}_{lang}.srt'
		srts[lang] = srt_path
		core(cache_data, srt_path, trans_map)
	return srts


def extra_sr_video_data(input_dir: str or Path, work_dir: str or Path, data_root: str or Path, gen_data_only=False):
	work_dir = Path(work_dir)
	data_root = Path(data_root)
	input_dir = Path(input_dir)
	text_map_root = data_root / 'TextMap'
	subtitle_root = work_dir / 'subtitles'
	raw_video_root = work_dir / 'tmp_video'
	fast_make_dir(subtitle_root, raw_video_root)

	with open(data_root / r'ExcelOutput\VideoConfig.json', 'rb') as f:
		data = json.load(f)
	config_map = {}
	for i in data.values():
		config_map[splitext(i['VideoPath'])[0]] = (i['CaptionPath'], i.get('VersionKey', 0))

	media_info = {}
	subtitle_info = {}
	tmp_files = []
	for i in input_dir.iterdir():
		if i.suffix != '.usm' or i.is_file() is False:
			continue
		name = i.stem
		if name.endswith('_m') or name.endswith('_f'):
			new_name = name[:-2]
		else:
			new_name = name
		caption_path, version_key = config_map.get(new_name, ('', 0))
		if new_name == "CS_Chap01_Act3010":
			version_key = 0
		tmp_files.append((i, name, caption_path, version_key))

	def extract_video(files):
		for i, name, _, version_key in files:
			output_video = raw_video_root / (name + '.ivf')
			if output_video.is_file():
				audios = {}
				for i in raw_video_root.iterdir():
					if i.name.startswith(name) and i.suffix == '.adx':
						inno = int(i.stem[i.stem.rfind('_') + 1:])
						audios[inno] = i
				data = (output_video, audios)
			else:
				data = test1_wrap(i, name, version_key, raw_video_root)
			media_info[name] = data

	extract_thread = pool.submit(extract_video, tmp_files)

	trans = {}
	for i in text_map_root.iterdir():
		if i.is_file() and i.name.startswith('TextMap'):
			trans[i.stem[7:].lower()] = SRTrans(i)
	print('trans加载成功')
	for _, name, caption_path, version_key in tmp_files:
		if not caption_path:
			continue
		srts = caption2srt(data_root / caption_path, trans, subtitle_root)
		subtitle_info[name] = srts
	print('等待视频解包完成')
	extract_thread.result()
	return [(value[0], {audio_lang[inno]: audio for inno, audio in value[1].items()}, subtitle_info.get(i, '')) for i, value in media_info.items()]


def gen_b_video(medias_info, work_dir: str or Path):
	work_dir = Path(work_dir)
	b_video_root = work_dir / 'b_video'
	b_video_root.mkdir(exist_ok=True)
	from ffmpeg_tool import gen_ffmpeg_cmd
	for video, audios, _ in medias_info:
		for lang, audio in audios.items():
			output_video = b_video_root / f'{video.stem}_{lang}.mp4'
			if output_video.is_file():
				continue
			gen_ffmpeg_cmd(video, {lang: audio}, None, b_video_root / f'{video.stem}_{lang}.mp4', audio_codec=('libvorbis', '-q:a', '30'))


def gen_full_video(medias_info, work_dir: str or Path):
	work_dir = Path(work_dir)
	combine_video_root = work_dir / 'videos'
	combine_video_root.mkdir(exist_ok=True)
	from ffmpeg_tool import gen_ffmpeg_cmd
	for video, audios, subtitles in medias_info:
		output_video = combine_video_root / (video.stem + '.mkv')
		if output_video.is_file():
			continue
		gen_ffmpeg_cmd(video, audios, subtitles, output_video, audio_codec=('libvorbis', '-q:a', '30'))


if __name__ == '__main__':
	input_dir = Path(r'D:\GameData\StarRail\Video\Windows')
	data_dir = Path(r'D:\starail\StarRailData')
	work_dir = Path(r'C:\Users\23117\.android\tmp')
	media_info = extra_sr_video_data(input_dir, work_dir, data_dir)
	gen_full_video(media_info, work_dir)

