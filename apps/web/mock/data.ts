export interface AudienceInfo {
  id: string
  name: string
  description: string
  avatar_url: string
  vrm_url: string
}

export const mockAudiences: AudienceInfo[] = [
  {
    id: 'Aini',
    name: '艾妮',
    description: '关心老人，温暖亲切，善于倾听，带来陪伴感',
    avatar_url: '/img/audiences/Aini.png',
    vrm_url: '',
  },
  {
    id: 'Liyin',
    name: '璃音',
    description: '妖媚诱惑、风情万种的性感',
    avatar_url: '/img/audiences/Liyin.png',
    vrm_url: '',
  },
  {
    id: 'Chuche',
    name: '初澈',
    description: '眼神中带着孩子般好奇，行动轻快又真诚',
    avatar_url: '/img/audiences/Chuche.jpg',
    vrm_url: '',
  },
  {
    id: 'Liulan',
    name: '流岚',
    description: '沉静而敏锐，总能在不经意间捕捉到微妙的情绪波动，像夜晚的星光般温柔而神秘',
    avatar_url: '/img/audiences/Liulan.jpg',
    vrm_url: '',
  },
  {
    id: 'Mengli',
    name: '萌莉',
    description: '自由洒脱，随性又略带调皮，总能轻松化解尴尬',
    avatar_url: '/img/audiences/Mengli.jpg',
    vrm_url: '',
  },
  {
    id: 'Qingyu',
    name: '卿羽',
    description: '温暖阳光般的存在，总能在平淡中带来一丝心动',
    avatar_url: '/img/audiences/Qingyu.jpg',
    vrm_url: '',
  },
  {
    id: 'Xingche',
    name: '星澈',
    description: '像流星划过天际，短暂而美丽，总让人回味',
    avatar_url: '/img/audiences/Xingche.jpg',
    vrm_url: '',
  },
  {
    id: 'Xueli',
    name: '雪砾',
    description: '温柔如风，轻轻一句话就能让心绪波动',
    avatar_url: '/img/audiences/Xueli.jpg',
    vrm_url: '',
  },
  {
    id: 'Youyao',
    name: '幼爻',
    description: '充满好奇心，总能用小动作带来惊喜感',
    avatar_url: '/img/audiences/Youyao.jpg',
    vrm_url: '',
  },
  {
    id: 'Yuxian',
    name: '鸢弦',
    description: '眼神中带着孩子般好奇，行动轻快又真诚',
    avatar_url: '/img/audiences/Yuxian.jpg',
    vrm_url: '',
  },
]

export const mockAuthUser = {
  user_id: 'mock_user_1',
  username: 'guest',
  display_name: '访客',
  role: 'user',
}
