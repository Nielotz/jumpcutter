$currentDirectory = Get-Item -Path (Get-Location)
$toProceedPath = $currentDirectory.FullName + "\To proceed\"

$toProceedFolder = Get-ChildItem $toProceedPath

Get-ChildItem $toProceedFolder -File -Recurse -Include "*.mp4", "*.mkv" | Foreach-Object {
    $file = $_

    Write-Host "Parsing: " $file

    # Remove static noise 

    # Reduce resolution and convert to mp4.
    Write-Host "Reducing resolution to 1600: "$fps
    $orygFullName = $file.FullName
    $tempFullName =  $file.Directory.FullName + "\" + "_" + $file.Name + ".mp4"
    .\ffmpeg.exe -threads 12 -i $orygFullName -vf scale=1600:-2,setsar=1:1 $tempFullName
    Start-Sleep -Seconds 2
    # Overwtire oryginal file
    mv -Force $tempFullName $orygFullName

    # Get FPS
    $_fpsCountOutput = .\ffprobe.exe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nw=1 $file
    $_fpsRatioOutput = $_fpsCountOutput.Split("=")[1]
    $_fpsRatioValues = $_fpsRatioOutput.Split("/")
    $fps = $_fpsRatioValues[0] / $_fpsRatioValues[1]

    Write-Host "FPS: "$fps

    # Speedup noise.
    $orygFullName = $file.FullName
    $tempFolderName = $file.Name.replace(" ", "").replace(".mp4", "")
    $tempFullName =  $file.Directory.FullName + "\" + "_" + $file.Name

    $jumpcutterParams = " --input_file " + '"\""' + $orygFullName + '\"""' +
                        " --output_file " + '"\""' + $tempFullName + '\"""' +
                        " --frame_rate " + $fps +
                        " --threads " + 12 +
                        " --temp_folder_name " + '"\""' + $tempFolderName + '\"""'
                        # " --temp_folder_name " + '"\""' + $tempFolderName + '\"""'
    $jumpcutterCommand = "python .\jumpcutter.py" + $jumpcutterParams
    Invoke-Expression $jumpcutterCommand
    Start-Sleep -Seconds 2
    # Overwtire oryginal file
    mv -Force $tempFullName $orygFullName
}