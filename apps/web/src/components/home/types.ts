export interface HomeCompanion {
  id: string
  name: string
  displayName: string
  subtitle: string
  description: string
  image: string
  heroImage: string
  tags: string[]
  skills: string[]
  relationship: string
  recent: string
  mood: string
  online: boolean
}

export interface SkillPackage {
  id: string
  title: string
  icon: string
  description: string
  suitable: string
  tone: 'green' | 'blue' | 'pink' | 'purple'
}
