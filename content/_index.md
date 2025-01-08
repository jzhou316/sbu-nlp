---
# Leave the homepage title empty to use the site title
title:
date: 2022-10-24
type: landing

design:
  # Default section spacing
  spacing: "6rem"

sections:
  - block: hero
    content:
      title: |
#        Stony Brook NLP
#      image:
#        filename: welcome.jpg
      text: |
        <br>
        
        The **Stony Brook Natural Language Processing (NLP)** has been a center of excellence for NLP and Artificial Intelligence research, teaching, and practice.
    
    design:
      spacing:
        padding: [10, 0, 0, 0]
        margin: [0, 0, 0, 0]
      # For full-screen, add `min-h-screen` below
      css_class: "dark"
      background:
        color: "navy"
        image:
          # Add your image background to `assets/media/`.
          filename: Web_Ready-231027_Fall Mall_008CSR.JPG
          filters:
            brightness: 0.5

  - block: markdown
    content:
      title:
      subtitle: ''
      text: |-
        Natural Language Processing (NLP) group at Stony Brook University is a team of researchers working on developing and studying state-of-the-art machine learning and computational methods for generating, analyzing and understanding language. Areas that we have particular strengths in include:

    - Human Centered NLP with applications to real world consequential tasks such as HealthCare, Writing Assistance
    - Evaluation of NLP technologies, resources, and human language use
    - Natural Language Generation
    - Efficiency in Model Algorithms, Training, and Inference
    - Morphology
    - Syntax and Semantics
    - Linguistic theories, Cognitive Modeling and Psycholinguistics
    - Dialogue, spoken language

    design:
      columns: '1'
#      background:
#        image: 
#          filename: coders.jpg
#          filters:
#            brightness: 1
#          parallax: false
#          position: center
#          size: cover
#          text_color_light: true
      spacing:
        padding: ['20px', '0', '20px', '0']
      css_class: fullscreen
  
  - block: collection
    content:
      title: Latest News
      subtitle:
      text:
      count: 5
      filters:
        author: ''
        category: ''
        exclude_featured: false
        publication_type: ''
        tag: ''
      offset: 0
      order: desc
      page_type: post
    design:
      view: card
      columns: '1'
  
  - block: markdown
    content:
      title:
      subtitle: ''
      text:
    design:
      columns: '1'
      background:
        image: 
          filename: coders.jpg
          filters:
            brightness: 1
          parallax: false
          position: center
          size: cover
          text_color_light: true
      spacing:
        padding: ['20px', '0', '20px', '0']
      css_class: fullscreen

  - block: collection
    content:
      title: Latest Preprints
      text: ""
      count: 5
      filters:
        folders:
          - publication
        publication_type: 'article'
    design:
      view: citation
      columns: '1'

  - block: markdown
    content:
      title:
      subtitle:
      text: |
        {{% cta cta_link="./people/" cta_text="Meet the team →" %}}
    design:
      columns: '1'
---
