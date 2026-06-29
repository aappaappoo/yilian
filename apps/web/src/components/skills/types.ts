export interface SkillPack {
  id: string
  title: string
  description: string
  category: string
  tags: string[]
  badge?: string
  priceLabel: string
  status: 'paid' | 'member-free' | 'vip' | 'trial' | 'learned'
  actionText: string
  icon: string
  accent: string
}

export interface SkillBundle {
  id: string
  title: string
  description: string
  price: string
  badge: string
  icon: string
}
