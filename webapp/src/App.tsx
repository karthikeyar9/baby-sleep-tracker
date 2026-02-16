// @ts-nocheck
import React, { useEffect, useState } from "react";
import Retrain from "./Retrain";
import CardPane from './card';
import VideoFeed, { VideoFeedTypeEnum } from './VideoFeed';
import SleepStats from './SleepStats';
import Charts from './Charts';
import Settings from './Settings';
import DiaperTracker from './DiaperTracker';
import SleepDashboard from './SleepDashboard';
import { csv } from './api/endpoints';

export function eventsWithinRange(events: any, startDate: any, endDate: any) {
  return events.filter((log: any) => {
    const logTime = log.time;
    return logTime > startDate && logTime < endDate;
  });
}

function App() {

  const [sleepLogs, setSleepLogs] = useState(null);
  const [forecast, setForecast] = useState(false);
  const [modelProba, setModelProba] = useState<any>(0.5);
  console.log('modelProba: ', modelProba);
  const [videoFeedType, setVideoFeedType] = useState<VideoFeedTypeEnum>(VideoFeedTypeEnum.RAW)

  useEffect(() => {
    csv.getSleepLogs(forecast).then(sleepLogs => {
      setSleepLogs(sleepLogs);
    });
  }, [forecast]);

  return (
    <div>
      <CardPane>
        <h2 style={{ color: 'orange' }}>The Baby Sleep Coach</h2>
      </CardPane>
      <CardPane>
        <SleepStats sleepLogs={sleepLogs} />
      </CardPane>
      <CardPane>
        <SleepDashboard />
      </CardPane>
      <CardPane>
        <DiaperTracker />
      </CardPane>
      <CardPane>
        <Retrain videoFeedType={videoFeedType} />
        <VideoFeed modelProba={modelProba} setModelProba={setModelProba} videoFeedType={videoFeedType} setVideoFeedType={setVideoFeedType} />
      </CardPane>

      <Charts sleepLogs={sleepLogs} forecast={forecast} setForecast={setForecast} />

      <CardPane>
        <Settings />
      </CardPane>
    </div>
  );
}

export default App
