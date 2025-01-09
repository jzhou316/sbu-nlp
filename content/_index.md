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
        Natural Language Processing (NLP) group at Stony Brook University is a team of researchers working on developing and studying state-of-the-art machine learning and computational methods for generating, analyzing and understanding language.
        Areas that we have particular strengths in include:
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
        padding: ['0', '0', '0', '0']
      css_class: fullscreen

  - block: markdown
    content:
      title: News
      subtitle: ''
      text: |-
        - PhD student [Harsh Trivedi](https://harshtrivedi.me/) wins [Best Resource Paper](https://aclanthology.org/2024.acl-long.850/) at ACL 2024 with [AppWorld](https://appworld.dev/)
        - New NLP Faculty [Jiawei (Joe) Zhou](https://joezhouai.com) joins Stony Brook University

    
  - block: collection
    content:
      title: Latest News
      subtitle:
      text:
      # Choose how many pages you would like to display (0 = all pages)
      count: 5
      # Filter on criteria
      filters:
        author: ''
        category: ''
        tag: ''
        exclude_featured: false
        exclude_future: false
        exclude_past: false
        publication_type: ''
      # Choose how many pages you would like to offset by
      offset: 0
      # Page order: descending (desc) or ascending (asc) date.
      order: desc
      # Page type to display. E.g. post, talk, publication...
      page_type: post
    design:
      # Choose a layout view
      view: date-title-summary.start
      columns: '1'
      # Reduce spacing
      spacing:
        padding: [0, 0, 0, 0]
  
#  - block: markdown
#    content:
#      title:
#      subtitle: ''
#      text:
#    design:
#      columns: '1'
#      background:
#        image: 
#          filename: coders.jpg
#         filters:
#            brightness: 1
#          parallax: false
#          position: center
#          size: cover
#          text_color_light: true
#      spacing:
#        padding: ['20px', '0', '20px', '0']
#      css_class: fullscreen

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
