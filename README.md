# Digital-Tool-Box-for-FDSA-Demo

This API based Digital Toolbox was designed and developed to automate the processing, analysis, and visualization of soundscape survey data. The web based interface allows users to upload one or multiple Excel datasets and obtain standardized soundscape analysis results through a single integrated workflow. The platform was developed in Python and implemented using a modular architecture that automatically detects the structure of uploaded datasets and determines the appropriate analytical procedures based on the available survey variables.
The toolbox incorporates established soundscape analysis methodologies, including ISO 12913 circumplex transformations, perceptual aggregation, normalization, density based visualization, and comparative soundscape plotting. Libraries such as Soundscapy, Pandas, NumPy, Seaborn, Matplotlib and Scikit-learn were utilized to support data processing, visualization, and statistical analysis. 
By combining data processing, statistical analysis and visualization within a single platform, the Digital Toolbox significantly reduces manual effort and improves the accessibility, reproducibility, and efficiency of soundscape research workflows.

Sample data templates can be found in the app/data folder to test with the interface

The developed web interface can be accessed through the following link: 
Digital Toolbox - https://digital-tool-box-ui.onrender.com/

### Technologies and Tools Used

Programming Language	- Python
Backend Framework	- FastAPI
API Development	- RESTful API Services
Data Processing	- Pandas, NumPy
Statistical Analysis -	Scikit-learn (PCA and dimensionality reduction)
Soundscape Analysis	- Soundscapy, ISO 12913 Framework
Data Visualization - Matplotlib, Seaborn
File Processing -	OpenPyXL, Excel (.xlsx) handling
Web Interface -	HTML, CSS, JavaScript
Data Exchange -	JSON
File Upload & Management - FastAPI UploadFile, Session based Storage
Cross Origin Communication - CORS Middleware
Development Environment - Jupyter Notebook
Version Control - GitHub
Deployment Platform	- Render Cloud Platform
Data Storage - Local File System, Metadata based History Management

### Features	
Multi file upload 
Toggle function for data connectors
Dataset preview
Automated plot generation  Session history Standardized Soundscape analysis pipeline

