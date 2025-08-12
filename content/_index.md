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
        Welcome to the Natural Language Processing (NLP) group at Stony Brook University. We are a team of researchers dedicated to developing and studying cutting-edge machine learning and computational methods for generating, analyzing, and understanding language.

        In the era of large language models (LLMs) and rapidly advancing artificial intelligence (AI), our work is at the forefront of the field. We focus on both in-depth and broad research to understand, improve, evaluate, and democratize the advanced technologies stemming from traditional and modern NLP.

        Our group's areas of expertise and active research include:
        - Language models (e.g., interpretability, development, architecture)
        - Natural language generation
        - Model efficiency (e.g., training/inference algorithms, hardware- and system-aware efficiency)
        - Evaluation of NLP technologies and human language use
        - Advanced LLM reasoning
        - Multimodal AI (e.g., vision-language models)
        - Agentic frameworks and benchmarks
        - Human-AI alignment and collaboration
        - Impact of generative AI
        - The fundamentals of language, including morphology, syntax, and semantics
        - Linguistic theories, Cognitive Modeling, and Psycholinguistics
        - Dialogue and spoken language


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
      # this makes the section take the full screen
#      css_class: fullscreen

  - block: markdown
    content:
      title: News
      subtitle: ''
      text: |-
        - [2025/08] New NLP faculty [Tuhin Chakrabarty](https://tuhinjubcse.github.io/) joins Stony Brook University
        - [2024/08] PhD student [Harsh Trivedi](https://harshtrivedi.me/) wins [Best Resource Paper](https://aclanthology.org/2024.acl-long.850/) at ACL 2024 with [AppWorld](https://appworld.dev/)
        - [2024/08] New NLP faculty [Jiawei (Joe) Zhou](https://joezhouai.com) joins Stony Brook University

    
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

#  - block: collection
#    content:
#      title: Latest Preprints
#      text: ""
#      count: 5
#      filters:
#        folders:
#          - publication
#        publication_type: 'article'
#    design:
#      view: citation
#      columns: '1'

  - block: markdown
    content:
      title:
      subtitle:
      text: |
        {{% cta cta_link="./people/" cta_text="Meet the team →" %}}
    design:
      columns: '1'
      spacing:
        padding: ['0', '0', '0', '0']
---
