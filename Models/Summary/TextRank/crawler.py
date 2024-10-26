import json
import regex as re
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def convert_time(start, end):
    '''
    아이폰 알람 설정처럼 사용자가 시작과 끝 시간을 입력하면 이를 crawler에서 활용할 수 있는 형태로 변환
    여기서는 입력 형태를 다음과 같다고 정의함 Ex) 00:00
    이후 시간 입력 형태 변화에 따라서 이 함수만 수정하면 됨
    +) start 혹은 end가 없다면 자동으로 처음과 끝을 지정하도록 추가해야 함
    '''
    
    start_min = int(start.split(':')[0])
    start_sec = int(start.split(':')[1])
    
    end_min = int(end.split(':')[0])
    end_sec = int(end.split(':')[1])

    return start_min * 60 + start_sec, end_min * 60 + end_sec


class YouTubeCaptionCrawler:
    def __init__(self, url, start=None, end=None):
        self.url = url
        self.ending_markers = ['는다', '니다', '는구나', '구나', '데요', 
                               '네요', '러요', '냐고', '아요', '어요', 
                               '가요', '군요', '래요', '랍니다', '습니까', 
                               '이죠', '겠죠', '겠네요', '까요', '랍니다', 
                               '였어요', '였네요', '시다', '이다', '이야',
                               '이죠', '겠죠', '나요', '려나', '려고',
                               '가죠', '나다', '라고', '라니', '라네']
        self.api_key = '--YOUR_API_KEY_HERE--'
        self.text = ""
        
        # 시간 지정이 있을 경우
        if start is not None and end is not None:
            self.start, self.end = convert_time(start, end)
        else:
            self.start, self.end = None, None

    ### helper functions
    
    def text_cleaning(self, text):
        if not isinstance(text, str):
            return text
        
        # Remove Special Texts
        text = re.sub(r'[☞▶◆#⊙※△▽▼□■◇◎☎○]+', '', text, flags=re.UNICODE)
        text = re.sub(r'〃', '', text)  
        text = re.sub(r'[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}]+', '', text, flags=re.UNICODE)
        text = re.sub(r'\[([^\]]{1,9})\]', '', text)
        text = re.sub(r'\[([^\]]{10,})\]', r'\1', text)
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'[\r\n]+', ' ', text)

        return text

    def get_video_id(self, url):
        if 'youtube.com/shorts/' in url:
            video_id = re.search(r'shorts/(.*?)\?feature', url).group(1)
        else:
            try:
                video_id = re.search(r'(?<=v=)[\w-]+', url).group(0)
            except AttributeError:
                video_id = re.search(r"youtu\.be\/([^/?]+)", url).group(1)
                
        return video_id
    
    def get_metadata(self, video_id):
        youtube = build('youtube', 'v3', developerKey=self.api_key)
        try:
            video_response = youtube.videos().list(
                part='snippet,statistics', 
                id=video_id
            ).execute()
            
            video_details = video_response['items'][0]['snippet']
            video_stats = video_response['items'][0]['statistics']
            
            video_title = video_details['title']
            upload_date = video_details['publishedAt']
            channel_id = video_details['channelId']
            channel_title = video_details['channelTitle']
            like_count = video_stats.get('likeCount', '0')
            hashtags = video_details.get('tags', [])
            thumbnails = video_details['thumbnails']['high']['url']
            
            details = {
                'video_title': video_title,
                'upload_date': upload_date,
                'channel_id': channel_id,
                'channel_title': channel_title,
                'like_count': like_count,
                'hashtags': hashtags,
                'thumbnails': thumbnails
            }
            
            return details
            
        except HttpError as e:
            print(f'HTTP Error {e.resp.status} has occurred: \n{e.content}')
            return None

    ### main functions
    
    def get_caption(self):
        # 영상 ID 가져오기
        video_id = self.get_video_id(self.url)
        
        # 자막 가져오기
        try: 
            caption = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko']) 
        except Exception:
            text = '해당 영상은 자동생성자막이 없거나 한국어 영상이 아닙니다.'
            return text
        
        # 시간 지정이 있을 경우
        if self.start is not None and self.end is not None:
            text = ' '.join([c['text'] for c in caption if self.start <= c['start'] <= self.end])
        # 시간 지정이 없을 경우
        else:
            text = ' '.join([c['text'] for c in caption])
        
        # 자막 전처리
        self.text = self.text_cleaning(text)
        
        return self.text

    def split_sentences(self):
        sentences = []
        start = 0
        for i in range(len(self.text)):
            for ending_marker in self.ending_markers:
                if self.text[i:].startswith(ending_marker):
                    sentence = self.text[start:i + len(ending_marker)].strip()
                    if sentence:
                        sentences.append(sentence)
                    start = i + len(ending_marker)
                    break

        last_sentence = self.text[start:].strip()
        if last_sentence:
            sentences.append(last_sentence)

        return sentences
    
    def save_to_json(self, file_path):
        video_id = self.get_video_id(self.url)
        details = self.get_metadata(video_id)
        captions = self.get_caption()
        if details:
            details['captions'] = captions
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(details, f, ensure_ascii=False, indent=4)
            print(f'Successfully saved JSON to {file_path}')
        else:
            print('JSON file not saved')