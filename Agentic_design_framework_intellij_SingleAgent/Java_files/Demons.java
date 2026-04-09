public class Demons extends Spirits{
    public void interactionH(Human myHuman){
    }
    public void interactionC(Creature myCreature){
        tranform(myCreature);
    }
    public void interactionA(Animal myAnimal){
    }

    private void tranform(Creature myCreature){}
}
