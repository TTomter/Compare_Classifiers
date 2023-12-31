"""
"""
import sys
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from astropy.coordinates import SkyCoord
from utilities.ipynb_docgen import capture_hide, show
import seaborn as sns
sns.set_theme(font_scale=1.25)
plt.rcParams['font.size']=14


from dataclasses import dataclass

@dataclass
class MLspec:
    features: tuple = tuple("""log_nbb log_epeak pindex curvature""".split())

    target : str ='association'
    target_names:tuple = tuple('bll fsrq psr'.split())

    def __repr__(self):
        return f"""
        Scikit-learn specifications: 
        * features: {self.features}
        * target: {self.target}
        * target_names: {self.target_names}"""

    
class FermiSources:
    """
    Manage the set of Fermi sources
    """
    
    def __init__(self, datafile= 'files/fermi_sources.csv',
                    selection='delta<0.25 & curvature<1.01'):
        
        t = pd.read_csv(datafile, index_col=0 )
        self.df = df = t.query(selection).copy()
        show(f"""Read {len(t)} source entries from `{datafile}`, selected {len(df)} with criteria '{selection}'""")  

        # descriptive rename and clean
        df.rename(columns=dict(singlat='sin_b', eflux100='eflux', variability='var',
                               category='association'),inplace=True)
        self.skycoord = SkyCoord(df.glon, df.glat, unit='deg', frame='galactic')
        #df.drop(columns='delta glat glon'.split(),inplace=True)
        # need log10 versions for sklearn
        df.loc[:,'log_nbb']   = np.log10(df.nbb.clip(1, 100))
        df.loc[:,'log_var']   = np.log10(df['var'].clip(0,1e4))
        df.loc[:,'log_eflux'] = np.log10(df.eflux.clip(1e-13,1e-9))
        df.loc[:,'log_e0']    = np.log10(df.e0)
        df.loc[:,'log_ts']    = np.log10(df.ts.clip(25,3316))
        df.loc[:,'abs_sin_b'] = np.abs(df.sin_b)

        # add log epeak, need lookup 
        sfl = SpecFunLookup(df) #[unid.index[1]]
        specfun = pd.Series(dict([ (idx,sfl[idx]) for idx in df.index]))
        df.loc[:,'log_epeak'] = specfun.apply(lambda f: f.sedfun.peak)

        self.mlspec = MLspec() # default for classificaiotn

    def show_data(self):
        """ Make a summary of the """
        df = self.df
        show(f"""* Summary of the numerical contents of selected data,<br>
        the "features" that can be used for population analysis.""")

        pd.set_option('display.precision', 3)
        show(df['eflux  pindex curvature e0 sin_b nbb var'.split()].describe(percentiles=[0.5]))
        show(r"""
            | Feature   | Description 
            |-------    | ----------- 
            |`eflux`    | Energy flux for E>100 Mev, in erg cm-2 s-1 
            |`pindex`   | Spectral index
            |`curvature`| Spectral curvature, the parameter $\beta$ for log-parabola
            |`e0`       | Spectral scale energy, close to the "pivot"
            |`sin_b`    | $\sin(b)$, where $b$ is the Galactic latitude 
            |`var`      | `Variability_Index` parameter from 4FGL-DR4 
            |`nbb`      | Number of Bayesian Block intervals from the wtlike analysis 
        """)

        show(f"""* Values and counts of the `category` column""")
        cats = np.unique(df.category) #= 'bll fsrq psr'.split()
        cnt = pd.Series(dict([(cat ,sum(df.category==cat)) for cat in cats]))
        show(cnt, index=False)
        
    def show_positions(self, xds,  caption=None):
        """
        * xds - a DataFrame with indexed wiht 4FGL names (like a dataset from here) and a `log_flux` column

        Show an Aitoff plot with the 
        """
        from wtlike.skymaps import AitoffFigure
        # Couldn't figure out how to modify my own code to avoid this warning
        import warnings
        # warnings.filterwarnings("ignore")
        def fxn():
            warnings.warn("deprecated", DeprecationWarning)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fxn()

        try:
            xpos = SkyCoord(pd.Series(self.skycoord, index=self.df.index)[xds.index].values)
        except Exception as msg:
            print(f"""Fail to get source positions: {msg} """, file=sys.stderr)
            return
        afig = AitoffFigure(figsize=(12,12))
        afig.ax.set_facecolor('lavender')
        scat = afig.scatter(xpos, c=xds.log_eflux);
        cb = plt.colorbar(scat,  shrink=0.35,
                        ticks=[-12,-11,-10], label='log Eflux');
        show(afig.fig, caption=caption)
    


    def getXy(self, mlspec=None) : #, features, target, target_names=None):
        """Return an X,y pair for ML training
        """
        if mlspec is not None:
            self.mlspec = mlspec
        ml = self.mlspec
        tsel = self.df[ml.target].apply(lambda c: c in ml.target_names)\
            if ml.target_names is not None else slice(None)
        assert sum(tsel)>0, 'No data selected for training.'
        return self.df.loc[tsel, ml.features], self.df.loc[tsel, ml.target]

    def fit(self, model, mlspec=None):
        """
        """
        X,y = self.getXy(mlspec) 
        return model.fit(X,y)

    def predict(self, classifier, query=None):
        """Return a "prediction" vector using the classifier, required to be a trained model

        - query -- optional query string

        return a Seriies 
        """
        # the feature names used for the classification -- expect all to be in the dataframe
        fnames = getattr(classifier, 'feature_names_in_', [])
        assert np.all(np.isin(fnames, self.df.columns)), f'classifier not set properly'
        dfq = self.df if query is None else self.df.query(query) 
        assert len(dfq)>0, 'No data selected'
        ypred = classifier.predict(dfq.loc[:,fnames])
        return pd.Series(ypred, index=dfq.index, name='prediction')
    
    def pairplot(self, **kwargs):
        
        ml = self.mlspec

        tsel = self.df[ml.target].apply(lambda c: c in ml.target_names)\
            if ml.target_names is not None else slice(None)
        kw = dict(kind='kde', hue=ml.target, height=2, )
        kw.update(**kwargs)
        sns.pairplot(self.df.loc[tsel], vars=ml.features,  **kw)
        return plt.gcf()
    
        
    def confusion_display(self, model=None, mlspec=None, **kwargs):
        """
        """
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, ConfusionMatrixDisplay 
        from sklearn.naive_bayes import GaussianNB 

        Xy = self.getXy(mlspec)
        split_kw = dict(test_size=0.25, shuffle=True)
        split_kw.update(kwargs)
        Xtrain, Xtest, ytrain, ytest  =  train_test_split(*Xy, **split_kw)

        model = GaussianNB()  if model is None else model     # 2. instantiate model
        classifier = model.fit(Xtrain, ytrain)     # 3. fit model to data
        y_model = model.predict(Xtest)             # 4. predict on new data

        show(f"""### Confusion matrix
        * Model: {model.__class__.__name__}<br>
        * Features: {list(Xy[0].columns)}<br>
        Accuracy: {100*accuracy_score(ytest, y_model):.0f}%
        """)

        fig, axx = plt.subplots(ncols=2, figsize=(12,5),
                               gridspec_kw=dict(wspace=0.4))
        # Plot non-normalized confusion matrix
        titles_options = [
            ("Unnormalization", None),
            ("Normalized", "true"),
        ]
        for ax, (title, normalize)  in zip(axx.flatten(), titles_options):
            disp = ConfusionMatrixDisplay.from_estimator(
                    classifier, Xtest, ytest,
                    display_labels='bll fsrq psr'.split(),
                    cmap=plt.cm.Blues,
                    normalize=normalize,
                    ax=ax,
                )

            ax.set_title(title)
        show(fig)

class SpecFunLookup:
    """dict allowing lookup of the uw spectral function name using 4FGL name

    df is indexed by fshas uw_name
    """
    def __init__(self, df):
        with capture_hide():
            from utilities.catalogs import UWcat
            uwcat = UWcat(filename = 'files/sources_uw1410.csv')

        self.d1 = dict(zip(df.index, df.uw_name));
        self.d2 = dict(zip(uwcat.jname, uwcat.specfunc))

    def __getitem__(self, catname):    
        return self.d2[self.d1[catname]]
    
    def get(self):
        return pd.Series(dict([ (idx, self[idx]) for idx in self.df.index]))



def show_unique(sclass):
    v,n = np.unique(sclass,  return_counts=True)
    show(
        pd.DataFrame.from_dict(
            dict(list(zip(v,n))), orient='index',
        )
     )

class SEDplotter:
    """ Manage SED plots showing both UW and 4FGL-DR4 

    """
    def __init__(self):
        """ set up the catalogs that have specfunc columns"""
        from utilities.catalogs import UWcat, Fermi4FGL
        self.uw = UWcat('uw1410')
        self.uw.index = self.uw.jname  # make it indexsed by the uw jname
        self.uw.index.name = 'UW jname'
        self.fcat = Fermi4FGL()
        self.plot_kw=[dict(lw=4,color='blue', alpha=0.5),dict(color='red')]
        
    def funcs(self, src):
        """ src is a Series object with index the 4FGL name, a "uw_name" entry
        return the spectral functions"""
        return self.uw.loc[src.uw_name,'specfunc'], self.fcat.loc[src.name,'specfunc']
        
    def plots(self, src, ax=None, **kwargs):
        fig, ax = plt.subplots(figsize=(2,2)) if ax is None else  (ax.figure, ax)
        kw = dict(xlabel='', ylabel=''); kw.update(kwargs)

        for f, pkw in zip(self.funcs(src), self.plot_kw):
            f.sed_plot(ax, plot_kw=pkw)
        ax.set(**kw)



def sedplotgrid(df, nrows=5,ncols=5, figsize=(8,8), **kwargs):
    
    def fmt_info(info, sep='\n  '):
        with pd.option_context('display.precision', 3):
            t = str(info).split('\n')[:-1]
        return info.name +sep+ sep.join(t)
    
    with capture_hide():
        sp = SEDplotter()
    
    fig, axx = plt.subplots(nrows=nrows, ncols=ncols, figsize=figsize,
                        sharex=True,sharey=True,
                       gridspec_kw=dict(top =0.99, bottom=0.01, hspace=0.1,
                                        left=0.01, right =0.99, wspace=0.1,))
    kw = dict(xticks=[], yticks=[], xlabel='', ylabel='', ylim=(0.02,10))    
    kw.update(kwargs)
    tt=[]
    for ax, (name,info) in zip(axx.flatten(), df.iterrows()):
        tt.append(fmt_info(info))
        sp.plots(info, ax=ax)
        ax.set(**kw)
    
    show(fig, 
         tooltips=tt, 
         caption=f"""Scales for x and y axes are {ax.get_xlim()} GeV and 
         {ax.get_ylim()} eV cm-2 s-1. uw1410 in blue, 4FGL in red.""")